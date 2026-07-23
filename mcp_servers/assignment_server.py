"""MCP server exposing the WRITE side: committing a crew assignment.

One tool: ``write_assignment``. It is reachable ONLY through the backend's
approval endpoint (invoked after a human clicks Approve) — it is never given to
the Claude agent. That separation is what enforces the success criterion:
no assignment is ever written without an approval click.

Runs over stdio; talks to the same local SQLite DB via DATABASE_URL with plain SQL.
"""
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine, text

load_dotenv()

# Defaults to the same absolute SQLite file the backend uses; set DATABASE_URL to
# the same hosted MySQL the backend uses so an assignment written here is the same
# one the dashboard reads back.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_URL = f"sqlite:///{os.path.join(_REPO_ROOT, 'maintenance_triage.sqlite3')}"


def _normalize_url(url: str) -> str:
    """Drop ssl-* query params from MySQL URLs (pymysql rejects ssl-mode; we do TLS
    via certifi in _connect_args instead)."""
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
        # Read the new id back by the unique work_order_id (portable SQL, no
        # dialect-specific RETURNING clause).
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
