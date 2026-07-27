"""Triage orchestration.

Flow (matches the architecture diagram):

    Work Orders DB
        -> read_queue (MCP tool, called by the agent itself)
        -> Claude agent proposes urgency + crew
        -> deterministic safety guard escalates injury-risk orders
        -> Proposal written (NOT an assignment)

``run_triage`` prefers ``agent.agentic_triage`` — a real Claude tool-use loop
that calls read_queue itself — falling back to the per-order
``agent.propose_triage`` path when there's no API key, on a rescan (mixed
pending+triaged queue), or if the agentic loop errors out. Crucially, the
agent is only ever given the *read* MCP tool. Nothing in this path can write
an assignment.
"""
import threading

from sqlalchemy.orm import Session

from backend.database import models
from backend.services import agent
from backend.services.mcp_client import QUEUE_SERVER, run_tool
from backend.services.safety_rules import apply_safety_override

# Guards against two overlapping triage runs racing over the same pending
# orders (which wastes Claude calls and can collide on the proposals table).
_triage_lock = threading.Lock()


def _read_queue(status: str):
    """Read work orders of a given lifecycle status through the queue MCP server."""
    return run_tool(QUEUE_SERVER, "read_queue", {"status": status})


def _pending_count(db: Session) -> int:
    return (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.status == models.STATUS_PENDING)
        .count()
    )


def _upsert_proposal(db: Session, work_order: models.WorkOrder, proposal_data: dict) -> models.Proposal:
    final_urgency, is_critical, keywords = apply_safety_override(
        work_order.description, proposal_data["urgency"]
    )
    # A pending order can never already have a proposal (that's what triaged
    # means), so skip the lazy-load lookup in that common case — it's an extra
    # round trip per order on a hosted DB otherwise.
    existing = None if work_order.status == models.STATUS_PENDING else work_order.proposal
    proposal = existing or models.Proposal(work_order_id=work_order.id)
    proposal.proposed_urgency = final_urgency
    proposal.proposed_crew = proposal_data["crew"]
    proposal.is_safety_critical = is_critical
    proposal.safety_keywords = ", ".join(keywords) if keywords else None
    proposal.reasoning = proposal_data.get("reasoning")
    proposal.confidence = proposal_data.get("confidence")
    proposal.source = proposal_data.get("source", "claude")

    if proposal.id is None:
        db.add(proposal)
    work_order.status = models.STATUS_TRIAGED
    return proposal


def stage_triage(db: Session, work_order: models.WorkOrder) -> bool:
    """Classify and upsert a proposal for one order, WITHOUT committing.

    Lets a caller triaging several orders in one pass (e.g. a generated batch)
    do a single commit at the end instead of one round trip per order — the
    dominant cost on a hosted DB, where each commit is real network latency.
    Best-effort: on failure nothing has touched the DB yet (propose_triage is
    a pure API/heuristic call, no writes happen until after it returns), so
    the caller's session stays perfectly usable for the next order.
    """
    try:
        proposal_data = agent.propose_triage(
            title=work_order.title,
            description=work_order.description,
            location=work_order.location,
        )
        _upsert_proposal(db, work_order, proposal_data)
        return True
    except Exception:
        return False


def triage_work_order(db: Session, work_order: models.WorkOrder) -> bool:
    """Triage and commit one work order in place — used for auto-triage on creation.

    Best-effort: on any failure the order is simply left ``pending`` (it can be
    picked up later by a manual Run triage) rather than raising, so a Claude
    hiccup never blocks an order from being filed. Returns True if triaged.
    """
    if not stage_triage(db, work_order):
        db.rollback()
        return False
    db.commit()
    return True


def _apply_agentic_proposals(db: Session, proposals: list[dict]) -> int:
    """Persist proposals Claude submitted via the agentic tool-use loop.

    Skips any work order the agent named that isn't actually still pending
    (e.g. a stale id) rather than failing the whole batch. One commit for the
    whole batch, not one per order — each commit is a real round trip on a
    hosted DB, and staging never touches the DB, so batching it is safe.
    """
    triaged = 0
    for proposal_data in proposals:
        work_order = db.get(models.WorkOrder, proposal_data.get("work_order_id"))
        if work_order is None or work_order.status != models.STATUS_PENDING:
            continue
        try:
            _upsert_proposal(db, work_order, proposal_data)
            triaged += 1
        except Exception:
            pass  # malformed proposal (e.g. a missing field) — skip it, keep the rest
    db.commit()
    return triaged


def run_triage(db: Session, rescan: bool = False, limit: int | None = None) -> dict:
    """Triage pending work orders. Returns a summary dict.

    Each order is committed as soon as it's triaged, so progress persists
    incrementally (a refresh mid-run shows partial results) and an interruption
    never loses completed work. A single failing order is skipped, not fatal.

    ``limit`` caps how many orders this call processes — the frontend calls in
    small chunks so it can show a live progress bar. ``rescan`` also re-runs
    already-triaged orders (never assigned/rejected ones) — that mixed queue
    doesn't fit the agentic loop's "read pending, triage it" contract, so a
    rescan always uses the per-order classic path. A module lock ensures only
    one run touches the queue at a time; a second caller returns busy.
    """
    if not _triage_lock.acquire(blocking=False):
        return {"triaged": 0, "queue_size": 0, "remaining": _pending_count(db), "busy": True}
    try:
        if not rescan:
            proposals = agent.agentic_triage(limit=limit or 8)
            if proposals is not None:
                triaged = _apply_agentic_proposals(db, proposals)
                return {
                    "triaged": triaged,
                    "queue_size": len(proposals),
                    "remaining": _pending_count(db),
                    "busy": False,
                }

        # Classic per-order fallback: no API key, agentic loop errored, or a
        # rescan (which re-triages already-triaged orders too).
        queue = _read_queue(models.STATUS_PENDING)
        if rescan:
            queue = queue + _read_queue(models.STATUS_TRIAGED)
        if limit is not None:
            queue = queue[:limit]

        triaged = 0
        for entry in queue:
            work_order = db.get(models.WorkOrder, entry["id"])
            if work_order is None:
                continue
            try:
                proposal_data = agent.propose_triage(
                    title=work_order.title,
                    description=work_order.description,
                    location=work_order.location,
                )
                _upsert_proposal(db, work_order, proposal_data)
                db.commit()  # persist this order immediately
                triaged += 1
            except Exception:
                db.rollback()  # skip the bad order, keep triaging the rest

        return {
            "triaged": triaged,
            "queue_size": len(queue),
            "remaining": _pending_count(db),
            "busy": False,
        }
    finally:
        _triage_lock.release()
