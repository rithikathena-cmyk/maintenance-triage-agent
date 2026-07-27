"""FastAPI application for the maintenance triage agent (standalone HTTP deploy).

Single-process deploys (Streamlit Community Cloud) use ``backend/local_client.py``
in-process instead — this app is for split hosting, where the frontend talks to
the backend over HTTP.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import assignments, workorders
from backend.database.database import init_db
from backend.services import health_service
from backend.services.safety_rules import CREWS, SAFETY_KEYWORDS, URGENCY_LEVELS


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Maintenance Triage Agent",
    description="Claude proposes urgency + crew; a human approves before any assignment is written.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(workorders.router)
app.include_router(assignments.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/full")
def health_full():
    """Live status of the DB, both MCP servers, and the Claude config."""
    return health_service.full_health("FastAPI")


@app.get("/meta")
def meta():
    """Domain vocabulary the frontend uses to render controls."""
    return {"crews": CREWS, "urgency_levels": URGENCY_LEVELS, "safety_keywords": SAFETY_KEYWORDS}
