"""MCP server exposing the WRITE side: committing a crew assignment.

One tool: ``write_assignment``. It is reachable ONLY through the backend's
approval endpoint (invoked after a human clicks Approve) — it is never given to
the Claude agent. That separation is what enforces the success criterion:
no assignment is ever written without an approval click.

Runs over stdio; talks to the same Postgres DB via DATABASE_URL with plain SQL.
"""
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:root@localhost:3306/maintenance_triage",
)


def _connect_args(url: str) -> dict:
    """Remote MySQL (TiDB Cloud) needs TLS verified via certifi; local MySQL
    ships a self-signed cert, so connect without verification there."""
    if not url.startswith("mysql"):
        return {}
    if "localhost" in url or "127.0.0.1" in url:
        return {}
    import certifi

    return {"ssl": {"ca": certifi.where()}}


_engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, future=True, connect_args=_connect_args(DATABASE_URL)
)

mcp = FastMCP("assignment-writer")


@mcp.tool()
def write_assignment(
    work_order_id: int,
    crew: str,
    urgency: str,
    is_safety_critical: bool,
    approved_by: str,
) -> str:
    """Commit a crew assignment for an approved work order.

    Creates a row in ``assignments`` and marks the work order ``assigned``.
    Refuses (idempotently) if the work order was already assigned.

    Returns:
        JSON object: {ok, assignment_id?, error?}.
    """
    with _engine.begin() as conn:
        wo = conn.execute(
            text("SELECT id, status FROM work_orders WHERE id = :id"),
            {"id": work_order_id},
        ).mappings().first()

        if wo is None:
            return json.dumps({"ok": False, "error": f"work_order {work_order_id} not found"})

        existing = conn.execute(
            text("SELECT id FROM assignments WHERE work_order_id = :id"),
            {"id": work_order_id},
        ).first()
        if existing is not None:
            return json.dumps(
                {"ok": False, "error": f"work_order {work_order_id} already assigned"}
            )

        conn.execute(
            text(
                """
                INSERT INTO assignments
                    (work_order_id, crew, urgency, is_safety_critical, approved_by, approved_at)
                VALUES
                    (:work_order_id, :crew, :urgency, :is_safety_critical, :approved_by, :approved_at)
                """
            ),
            {
                "work_order_id": work_order_id,
                "crew": crew,
                "urgency": urgency,
                "is_safety_critical": is_safety_critical,
                "approved_by": approved_by,
                "approved_at": datetime.utcnow(),
            },
        )
        # Read the new id back by the unique work_order_id — portable across
        # Postgres and MySQL/TiDB (avoids the Postgres-only RETURNING clause).
        assignment_id = conn.execute(
            text("SELECT id FROM assignments WHERE work_order_id = :id"),
            {"id": work_order_id},
        ).scalar_one()

        conn.execute(
            text("UPDATE work_orders SET status = 'assigned' WHERE id = :id"),
            {"id": work_order_id},
        )

    return json.dumps({"ok": True, "assignment_id": assignment_id})


if __name__ == "__main__":
    mcp.run()
