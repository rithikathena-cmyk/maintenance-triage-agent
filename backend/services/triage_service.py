"""Triage orchestration.

Flow (matches the architecture diagram):

    Work Orders DB
        -> read_queue (MCP tool)
        -> Claude agent proposes urgency + crew
        -> deterministic safety guard escalates injury-risk orders
        -> Proposal written (NOT an assignment)

Crucially, the agent is only ever given the *read* MCP tool here. Nothing in
this path can write an assignment.
"""
import threading

from sqlalchemy.orm import Session

from backend.database import models
from backend.services import claude_service
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
    proposal = work_order.proposal or models.Proposal(work_order_id=work_order.id)
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


def triage_work_order(db: Session, work_order: models.WorkOrder) -> bool:
    """Triage one work order in place — used for auto-triage on creation.

    Best-effort: on any failure the order is simply left ``pending`` (it can be
    picked up later by a manual Run triage) rather than raising, so a Claude
    hiccup never blocks an order from being filed. Returns True if triaged.
    """
    try:
        proposal_data = claude_service.propose_triage(
            title=work_order.title,
            description=work_order.description,
            location=work_order.location,
        )
        _upsert_proposal(db, work_order, proposal_data)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def run_triage(db: Session, rescan: bool = False, limit: int | None = None) -> dict:
    """Triage pending work orders. Returns a summary dict.

    Each order is committed as soon as it's triaged, so progress persists
    incrementally (a refresh mid-run shows partial results) and an interruption
    never loses completed work. A single failing order is skipped, not fatal.

    ``limit`` caps how many orders this call processes — the frontend calls in
    small chunks so it can show a live progress bar. ``rescan`` also re-runs
    already-triaged orders (never assigned/rejected ones). A module lock ensures
    only one run touches the queue at a time; a second caller returns busy.
    """
    if not _triage_lock.acquire(blocking=False):
        return {"triaged": 0, "queue_size": 0, "remaining": _pending_count(db), "busy": True}
    try:
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
                proposal_data = claude_service.propose_triage(
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
