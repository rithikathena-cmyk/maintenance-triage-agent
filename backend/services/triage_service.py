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
from sqlalchemy.orm import Session

from backend.database import models
from backend.services import claude_service
from backend.services.mcp_client import QUEUE_SERVER, run_tool
from backend.services.safety_rules import apply_safety_override


def _read_queue(status: str):
    """Read work orders of a given lifecycle status through the queue MCP server."""
    return run_tool(QUEUE_SERVER, "read_queue", {"status": status})


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


def run_triage(db: Session, rescan: bool = False) -> dict:
    """Triage pending work orders. Returns a summary dict.

    When ``rescan`` is set, orders already triaged (but not yet assigned or
    rejected) are re-run through the agent too — useful for refreshing proposals
    after a prompt change. Assigned/rejected orders are never re-triaged.
    """
    queue = _read_queue(models.STATUS_PENDING)
    if rescan:
        queue = queue + _read_queue(models.STATUS_TRIAGED)

    triaged = 0
    for entry in queue:
        work_order = db.get(models.WorkOrder, entry["id"])
        if work_order is None:
            continue
        proposal_data = claude_service.propose_triage(
            title=work_order.title,
            description=work_order.description,
            location=work_order.location,
        )
        _upsert_proposal(db, work_order, proposal_data)
        triaged += 1

    db.commit()
    return {"triaged": triaged, "queue_size": len(queue)}
