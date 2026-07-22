"""SQLAlchemy engine / session wiring for the maintenance_triage database."""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/maintenance_triage",
)


def connect_args_for(url: str) -> dict:
    """Extra connect args per backend.

    TiDB Cloud (and hosted MySQL generally) require a TLS connection; we verify
    the server against the certifi CA bundle. Postgres/local needs nothing.
    """
    if url.startswith("mysql"):
        import certifi

        return {"ssl": {"ca": certifi.where()}}
    return {}


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
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


# Columns added after the initial schema shipped. create_all() never ALTERs an
# existing table, so we additively backfill new columns here (idempotent — each
# is guarded by IF NOT EXISTS). Keeps existing seeded data intact across upgrades.
_ADDITIVE_MIGRATIONS = (
    "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION",
    "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS rejected_by VARCHAR(120)",
    "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS rejected_reason TEXT",
    "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP",
)


def init_db():
    """Create all tables and apply additive migrations. Safe to call repeatedly."""
    from backend.database import models  # noqa: F401 — register models on Base

    Base.metadata.create_all(bind=engine)

    # The additive migrations use Postgres-specific DDL (ADD COLUMN IF NOT
    # EXISTS, DOUBLE PRECISION) and only matter when upgrading a pre-existing
    # Postgres schema. On a fresh database (e.g. TiDB/MySQL), create_all above
    # already builds every column, so we skip them off Postgres.
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for statement in _ADDITIVE_MIGRATIONS:
            conn.execute(text(statement))
