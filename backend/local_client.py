"""In-process backend for the single-process (Streamlit Community Cloud) deploy.

The whole backend runs *inside* the Streamlit process — no FastAPI server, no
HTTP hop. Each call opens a short-lived DB session, invokes the service layer,
and returns the same JSON-shaped data the old HTTP endpoints returned, so the
frontend's ``api_get`` / ``api_post`` keep working unchanged — just without the
network. ``get`` / ``post`` dispatch by path to mirror the old REST surface.

Requires DATABASE_URL / ANTHROPIC_API_KEY in the environment (the frontend
bridges Streamlit secrets into os.environ before importing this module).
"""
import os
import re

from sqlalchemy import text

from backend.database import models
from backend.database.database import (
    SessionLocal,
    engine,
    init_db,
)
from backend.schemas.schemas import AssignmentOut, ProposalOut, WorkOrderOut
from backend.services import agent_service, assignment_service, triage_service
from backend.services.mcp_client import ASSIGNMENT_SERVER, QUEUE_SERVER, ping_server
from backend.services.safety_rules import (
    CREWS,
    SAFETY_KEYWORDS,
    URGENCY_LEVELS,
    urgency_rank,
)

_initialized = False


def ensure_init():
    """Create tables once per process. No auto-seed — the queue is populated
    manually via the sidebar "Generate next batch of orders" button."""
    global _initialized
    if _initialized:
        return
    init_db()
    _initialized = True


# --------------------------------------------------------------------------- #
# Serializers
# --------------------------------------------------------------------------- #
def _proposal_dict(p: models.Proposal) -> dict:
    wo = p.work_order
    kws = [k.strip() for k in (p.safety_keywords or "").split(",") if k.strip()]
    return ProposalOut(
        work_order_id=wo.id,
        title=wo.title,
        description=wo.description,
        location=wo.location,
        reported_by=wo.reported_by,
        status=wo.status,
        proposed_urgency=p.proposed_urgency,
        proposed_crew=p.proposed_crew,
        is_safety_critical=p.is_safety_critical,
        safety_keywords=kws,
        reasoning=p.reasoning,
        confidence=p.confidence,
        source=p.source,
        created_at=wo.created_at,
    ).model_dump(mode="json")


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
def _check_database() -> dict:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "up", "detail": "connected"}
    except Exception as exc:
        return {"status": "down", "detail": exc.__class__.__name__}


def _check_mcp(server: str, tool: str) -> dict:
    try:
        tools = ping_server(server)
    except Exception as exc:
        return {"status": "down", "detail": exc.__class__.__name__}
    if tool not in tools:
        return {"status": "degraded", "detail": f"missing {tool}"}
    return {"status": "up", "detail": f"{len(tools)} tool(s): {', '.join(tools)}"}


def _check_claude() -> dict:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"status": "fallback", "detail": "no API key — keyword heuristic"}
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return {"status": "fallback", "detail": "anthropic SDK not installed"}
    return {"status": "configured", "detail": os.getenv("CLAUDE_MODEL", "claude-opus-4-8")}


def _health_full() -> dict:
    comps = {
        "backend": {"status": "up", "detail": "in-process"},
        "database": _check_database(),
        "queue_mcp": _check_mcp(QUEUE_SERVER, "read_queue"),
        "assignment_mcp": _check_mcp(ASSIGNMENT_SERVER, "write_assignment"),
        "claude": _check_claude(),
    }
    healthy = {"up", "configured"}
    overall = "ok" if all(c["status"] in healthy for c in comps.values()) else "degraded"
    return {"status": overall, "components": comps}


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def _stats() -> dict:
    db = SessionLocal()
    try:
        WO = models.WorkOrder

        def c(status):
            return db.query(WO).filter(WO.status == status).count()

        pend, aw, asg, rej = c("pending"), c("triaged"), c("assigned"), c("rejected")
        safety = (
            db.query(models.Proposal)
            .join(WO)
            .filter(WO.status == "triaged", models.Proposal.is_safety_critical.is_(True))
            .count()
        )
        return {
            "open_orders": pend + aw,
            "safety_cases": safety,
            "awaiting_review": aw,
            "assigned": asg,
            "rejected": rej,
            "pending_triage": pend,
        }
    finally:
        db.close()


def _proposals() -> list:
    db = SessionLocal()
    try:
        rows = (
            db.query(models.Proposal)
            .join(models.WorkOrder)
            .filter(models.WorkOrder.status == "triaged")
            .all()
        )
        rows.sort(
            key=lambda p: (
                0 if p.is_safety_critical else 1,
                urgency_rank(p.proposed_urgency),
                p.work_order.created_at,
            )
        )
        return [_proposal_dict(p) for p in rows]
    finally:
        db.close()


def _assignments() -> list:
    db = SessionLocal()
    try:
        rows = db.query(models.Assignment).order_by(models.Assignment.approved_at.desc()).all()
        return [AssignmentOut.model_validate(a).model_dump(mode="json") for a in rows]
    finally:
        db.close()


def _work_orders(status=None) -> list:
    db = SessionLocal()
    try:
        q = db.query(models.WorkOrder)
        if status:
            q = q.filter(models.WorkOrder.status == status)
        rows = q.order_by(models.WorkOrder.created_at.asc()).all()
        return [WorkOrderOut.model_validate(w).model_dump(mode="json") for w in rows]
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def _triage(limit=None, agentic=False, rescan=False) -> dict:
    db = SessionLocal()
    try:
        if agentic:
            return agent_service.agentic_triage(db, limit=limit or 8)
        return triage_service.run_triage(db, rescan=rescan, limit=limit)
    finally:
        db.close()


def add_sample_batch(index: int) -> dict:
    """Reveal the next set (page) of the 50-order sample pool.

    Inserts the ``index``-th chunk of ``BATCH_SIZE`` orders (skipping any titles
    already present), then triages ONLY those new orders directly — no MCP
    round-trip, so it always produces reviewable cards even on Streamlit Cloud.
    Never assigns; the dispatcher approves/rejects each card manually.
    """
    from backend.database.sample_orders import BATCH_SIZE, SAMPLE_ORDERS

    ensure_init()
    total_sets = (len(SAMPLE_ORDERS) + BATCH_SIZE - 1) // BATCH_SIZE
    start = index * BATCH_SIZE
    chunk = SAMPLE_ORDERS[start:start + BATCH_SIZE]

    db = SessionLocal()
    try:
        existing = {t for (t,) in db.query(models.WorkOrder.title).all()}
        new_ids = []
        for order in chunk:
            if order["title"] in existing:
                continue
            wo = models.WorkOrder(status=models.STATUS_PENDING, **order)
            db.add(wo)
            db.flush()  # assign wo.id without ending the transaction
            new_ids.append(wo.id)
        db.commit()

        # Triage each new order in place (propose urgency/crew → a reviewable
        # proposal). This is the deterministic path; it never assigns.
        for wid in new_ids:
            wo = db.get(models.WorkOrder, wid)
            if wo is not None:
                triage_service.triage_work_order(db, wo)
    finally:
        db.close()

    return {
        "added": len(new_ids),
        "batch_no": min(index + 1, total_sets),
        "total_batches": total_sets,
        "exhausted": start >= len(SAMPLE_ORDERS),
    }


def dispatch_stream(actor: str = "Claude agent", limit: int = 25):
    """Stream the autonomous dispatcher's live tool activity (a generator).

    Opens one DB session for the whole agent loop and yields the event dicts
    from ``agent_service.agentic_dispatch`` straight through to the caller
    (the Streamlit frontend renders them into a live feed).
    """
    ensure_init()
    db = SessionLocal()
    try:
        yield from agent_service.agentic_dispatch(db, actor=actor, limit=limit)
    finally:
        db.close()


def _create_work_order(payload: dict) -> dict:
    db = SessionLocal()
    try:
        wo = models.WorkOrder(
            title=payload["title"],
            description=payload["description"],
            location=payload.get("location"),
            reported_by=payload.get("reported_by"),
            status=models.STATUS_PENDING,
        )
        db.add(wo)
        db.commit()
        db.refresh(wo)
        triage_service.triage_work_order(db, wo)  # auto-triage
        db.refresh(wo)
        return WorkOrderOut.model_validate(wo).model_dump(mode="json")
    finally:
        db.close()


def _approve(work_order_id, approved_by, crew=None) -> dict:
    db = SessionLocal()
    try:
        a = assignment_service.approve(
            db, work_order_id=work_order_id, approved_by=approved_by, crew_override=crew
        )
        return AssignmentOut.model_validate(a).model_dump(mode="json")
    finally:
        db.close()


def _change_crew(work_order_id, crew) -> dict:
    db = SessionLocal()
    try:
        return _proposal_dict(assignment_service.change_crew(db, work_order_id, crew))
    finally:
        db.close()


def _reject(work_order_id, rejected_by, reason=None) -> dict:
    db = SessionLocal()
    try:
        w = assignment_service.reject(db, work_order_id, rejected_by=rejected_by, reason=reason)
        return WorkOrderOut.model_validate(w).model_dump(mode="json")
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Dispatch — mirrors the old REST surface so the frontend is unchanged
# --------------------------------------------------------------------------- #
_PROP_RE = re.compile(r"^/proposals/(\d+)/(change-crew|reject)$")


def get(path, **params):
    ensure_init()
    if path == "/health":
        return {"status": "ok"}
    if path == "/health/full":
        return _health_full()
    if path == "/meta":
        return {"crews": CREWS, "urgency_levels": URGENCY_LEVELS, "safety_keywords": SAFETY_KEYWORDS}
    if path == "/stats":
        return _stats()
    if path == "/proposals":
        return _proposals()
    if path == "/assignments":
        return _assignments()
    if path == "/work-orders":
        return _work_orders(status=params.get("status"))
    raise ValueError(f"unknown GET {path}")


def post(path, json=None, **params):
    ensure_init()
    body = json or {}
    if path == "/triage":
        return _triage(
            limit=params.get("limit"),
            agentic=bool(params.get("agentic", False)),
            rescan=bool(params.get("rescan", False)),
        )
    if path == "/work-orders":
        return _create_work_order(body)
    if path == "/assignments/approve":
        return _approve(params["work_order_id"], approved_by=body["approved_by"], crew=body.get("crew"))
    m = _PROP_RE.match(path)
    if m:
        wid = int(m.group(1))
        if m.group(2) == "change-crew":
            return _change_crew(wid, body["crew"])
        return _reject(wid, rejected_by=body["rejected_by"], reason=body.get("reason"))
    raise ValueError(f"unknown POST {path}")
