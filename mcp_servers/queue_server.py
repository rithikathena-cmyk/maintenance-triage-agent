"""MCP server exposing the READ side of the work-order queue.

One tool: ``read_queue`` — returns incoming work orders for the agent to triage.
This is the only DB-facing tool the Claude agent is ever given, which is what
guarantees the agent can never write an assignment on its own.

Runs over stdio (``python mcp_servers/queue_server.py``); the backend spawns it
as an MCP client. It talks to the same local SQLite database via DATABASE_URL and
uses plain SQL so it stays independent of the backend package.
"""
import json
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine, text

load_dotenv()

# Defaults to the same absolute SQLite file the backend uses (repo root /
# maintenance_triage.sqlite3); set DATABASE_URL to the same hosted MySQL the
# backend uses so this server reads the exact same queue the dashboard shows.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_URL = f"sqlite:///{os.path.join(_REPO_ROOT, 'maintenance_triage.sqlite3')}"


def _normalize_url(url: str) -> str:
    """Force the pymysql driver for bare mysql:// URLs and drop ssl-* query params
    (pymysql rejects ssl-mode; we do TLS via certifi in _connect_args instead)."""
    if url.startswith("mysql://"):
        url = "mysql+pymysql://" + url[len("mysql://"):]
    if not url.startswith("mysql"):
        return url
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("ssl")]
    return urlunsplit(parts._replace(query=urlencode(kept)))


DATABASE_URL = _normalize_url(os.getenv("DATABASE_URL", _DEFAULT_URL))


def _connect_args(url: str) -> dict:
    """SQLite needs check_same_thread; hosted MySQL uses encrypted TLS (hosted
    providers sign with a private CA, so we don't verify the public CA)."""
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("mysql") and not ("localhost" in url or "127.0.0.1" in url):
        import ssl

        ca = os.getenv("DB_SSL_CA")
        if ca:
            return {"ssl": ssl.create_default_context(cafile=ca)}
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return {"ssl": ctx}
    return {}


_engine = create_engine(
    DATABASE_URL, future=True, pool_pre_ping=True, connect_args=_connect_args(DATABASE_URL)
)

mcp = FastMCP("work-order-queue")


@mcp.tool()
def read_queue(status: str = "pending", limit: int = 100) -> str:
    """Read work orders from the queue.

    Args:
        status: Lifecycle status to filter by (default "pending").
        limit: Maximum number of orders to return.

    Returns:
        JSON array of work orders (id, title, description, location,
        reported_by, status, created_at).
    """
    sql = text(
        """
        SELECT id, title, description, location, reported_by, status, created_at
        FROM work_orders
        WHERE status = :status
        ORDER BY created_at ASC
        LIMIT :limit
        """
    )
    with _engine.connect() as conn:
        rows = conn.execute(sql, {"status": status, "limit": limit}).mappings().all()

    orders = [
        {
            "id": r["id"],
            "title": r["title"],
            "description": r["description"],
            "location": r["location"],
            "reported_by": r["reported_by"],
            "status": r["status"],
            "created_at": (
                r["created_at"].isoformat()
                if hasattr(r["created_at"], "isoformat")
                else r["created_at"]
            ),
        }
        for r in rows
    ]
    return json.dumps(orders)


if __name__ == "__main__":
    mcp.run()
