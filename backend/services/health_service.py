"""Subsystem health checks shared by the FastAPI app and the in-process client."""
import os

from sqlalchemy import text

from backend.database.database import engine
from backend.services.mcp_client import ASSIGNMENT_SERVER, QUEUE_SERVER, ping_server

_HEALTHY_STATUSES = {"up", "configured"}


def check_database() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "up", "detail": "connected"}
    except Exception as exc:
        return {"status": "down", "detail": exc.__class__.__name__}


def check_mcp(server_script: str, expected_tool: str) -> dict:
    try:
        tools = ping_server(server_script)
    except Exception as exc:
        return {"status": "down", "detail": exc.__class__.__name__}
    if expected_tool not in tools:
        return {"status": "degraded", "detail": f"missing tool '{expected_tool}'"}
    return {"status": "up", "detail": f"{len(tools)} tool(s): {', '.join(tools)}"}


def check_claude() -> dict:
    """Config-level check (key present + SDK importable).

    Deliberately does NOT make a billable API round-trip on every page load;
    'configured' means triage will use the real model, 'fallback' means it will
    transparently use the keyword heuristic instead.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"status": "fallback", "detail": "no API key — keyword heuristic"}
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return {"status": "fallback", "detail": "anthropic SDK not installed"}
    return {"status": "configured", "detail": os.getenv("CLAUDE_MODEL", "claude-sonnet-5")}


def full_health(backend_detail: str) -> dict:
    """Live status of every subsystem, for the dashboard header."""
    components = {
        "backend": {"status": "up", "detail": backend_detail},
        "database": check_database(),
        "queue_mcp": check_mcp(QUEUE_SERVER, "read_queue"),
        "assignment_mcp": check_mcp(ASSIGNMENT_SERVER, "write_assignment"),
        "claude": check_claude(),
    }
    overall = "ok" if all(c["status"] in _HEALTHY_STATUSES for c in components.values()) else "degraded"
    return {"status": overall, "components": components}
