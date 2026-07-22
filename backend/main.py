"""FastAPI application for the maintenance triage agent."""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api import assignments, workorders
from backend.database.database import engine, init_db
from backend.services.mcp_client import (
    ASSIGNMENT_SERVER,
    QUEUE_SERVER,
    ping_server,
)
from backend.services.safety_rules import CREWS, SAFETY_KEYWORDS, URGENCY_LEVELS


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Optional one-shot seed for fresh cloud deployments (Render, etc.) where
    # there's no shell to run `python -m backend.database.seed`. seed() itself
    # is a no-op if the table is already populated, so this stays idempotent.
    if os.getenv("SEED_ON_START", "").lower() in ("1", "true", "yes"):
        try:
            from backend.database.seed import seed

            seed()
        except Exception as exc:  # never block startup on a seed hiccup
            print(f"[startup] seed skipped: {exc!r}")
    yield


app = FastAPI(
    title="Maintenance Triage Agent",
    description="Claude proposes urgency + crew; a human approves before any assignment is written.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Full subsystem health — probes the DB, both MCP servers, and the Claude
# config. Spawning MCP servers is ~1s each, so results are memoized briefly.
# --------------------------------------------------------------------------- #
_HEALTH_TTL = 10.0  # seconds
_health_cache: dict = {"ts": 0.0, "data": None}


def _check_database() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "up", "detail": "connected"}
    except Exception as exc:
        return {"status": "down", "detail": exc.__class__.__name__}


def _check_mcp(server_script: str, expected_tool: str) -> dict:
    try:
        tools = ping_server(server_script)
    except Exception as exc:
        return {"status": "down", "detail": exc.__class__.__name__}
    if expected_tool not in tools:
        return {"status": "degraded", "detail": f"missing tool '{expected_tool}'"}
    return {"status": "up", "detail": f"{len(tools)} tool(s): {', '.join(tools)}"}


def _check_claude() -> dict:
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
    return {"status": "configured", "detail": os.getenv("CLAUDE_MODEL", "claude-opus-4-8")}


def _compute_health() -> dict:
    components = {
        "backend": {"status": "up", "detail": "FastAPI"},
        "database": _check_database(),
        "queue_mcp": _check_mcp(QUEUE_SERVER, "read_queue"),
        "assignment_mcp": _check_mcp(ASSIGNMENT_SERVER, "write_assignment"),
        "claude": _check_claude(),
    }
    healthy = {"up", "configured"}
    overall = "ok" if all(c["status"] in healthy for c in components.values()) else "degraded"
    return {"status": overall, "components": components}


@app.get("/health/full")
def health_full():
    """Live subsystem status for the dashboard header (briefly cached)."""
    now = time.monotonic()
    if _health_cache["data"] is not None and now - _health_cache["ts"] < _HEALTH_TTL:
        return _health_cache["data"]
    data = _compute_health()
    _health_cache.update(ts=now, data=data)
    return data


@app.get("/meta")
def meta():
    """Domain vocabulary the frontend uses to render controls."""
    return {
        "crews": CREWS,
        "urgency_levels": URGENCY_LEVELS,
        "safety_keywords": SAFETY_KEYWORDS,
    }


app.include_router(workorders.router)
app.include_router(assignments.router)
