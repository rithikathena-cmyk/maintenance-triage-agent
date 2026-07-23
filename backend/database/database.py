"""SQLAlchemy engine / session wiring.

Default: a local SQLite file at the repo root — zero setup, used for local dev
and quick demos. Set DATABASE_URL to a hosted MySQL (e.g. Aiven) for persistent
data that survives restarts. The connect settings are chosen per dialect, so the
same code works for SQLite locally and hosted MySQL in the cloud.
"""
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# Repo root = two levels up from this file (backend/database/database.py).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SQLITE_PATH = os.path.join(_REPO_ROOT, "maintenance_triage.sqlite3")


def normalize_url(url: str) -> str:
    """Strip ``ssl-*`` query params from MySQL URLs.

    Hosted MySQL providers (Aiven, etc.) hand you a URL ending in
    ``?ssl-mode=REQUIRED``, but pymysql doesn't accept ``ssl-mode`` as a connect
    kwarg and raises TypeError. We enforce TLS ourselves via certifi in
    ``connect_args_for``, so these URL params are redundant — drop them.
    """
    if not url.startswith("mysql"):
        return url
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("ssl")]
    return urlunsplit(parts._replace(query=urlencode(kept)))


# Local SQLite by default (absolute path so every process opens the same file).
# Override with a hosted URL, e.g.
#   mysql+pymysql://user:pass@host:port/maintenance_triage   (Aiven MySQL)
DATABASE_URL = normalize_url(os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}"))


def _mysql_ssl_context():
    """Encrypted TLS for hosted MySQL, without public-CA verification.

    Hosted providers like Aiven sign their server cert with their OWN private CA,
    which isn't in the public certifi bundle — so verifying against certifi fails
    with "self-signed certificate in certificate chain". The connection is still
    encrypted; we just don't verify the CA. To fully verify instead, download the
    provider's ca.pem and set DB_SSL_CA to its path.
    """
    import ssl

    ca = os.getenv("DB_SSL_CA")
    if ca:
        return ssl.create_default_context(cafile=ca)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def connect_args_for(url: str) -> dict:
    """Connect args per database dialect.

    - SQLite: ``check_same_thread=False`` — Streamlit runs the script in a worker
      thread separate from the one that opened the pooled connection.
    - Hosted MySQL (Aiven, etc.): encrypted TLS (see ``_mysql_ssl_context``), plus
      a short ``connect_timeout`` so an unreachable host fails fast on startup.
    - Local MySQL (localhost): plaintext, no TLS.
    - Postgres / anything else: no extra args (put ``?sslmode=require`` in the URL).
    """
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("mysql"):
        if "localhost" in url or "127.0.0.1" in url:
            return {}
        return {"ssl": _mysql_ssl_context(), "connect_timeout": 8}
    return {}


engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args_for(DATABASE_URL),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Safe to call repeatedly (create_all is idempotent)."""
    from backend.database import models  # noqa: F401 — register models on Base

    Base.metadata.create_all(bind=engine)
