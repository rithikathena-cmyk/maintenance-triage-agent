"""MCP server exposing the READ side of the work-order queue.

One tool: ``read_queue`` — returns incoming work orders for the agent to triage.
This is the only DB-facing tool the Claude agent is ever given, which is what
guarantees the agent can never write an assignment on its own.

Runs over stdio (``python mcp_servers/queue_server.py``); the backend spawns it
as an MCP client. It talks to the same Postgres database via DATABASE_URL and
uses plain SQL so it stays independent of the backend package.
"""
import json
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/maintenance_triage",
)


def _connect_args(url: str) -> dict:
    """TiDB Cloud / hosted MySQL require TLS; verify against the certifi bundle."""
    if url.startswith("mysql"):
        import certifi

        return {"ssl": {"ca": certifi.where()}}
    return {}


_engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, future=True, connect_args=_connect_args(DATABASE_URL)
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
