"""Assignment orchestration — the human-approval side of the flow.

``approve`` is the ONLY path that reaches the write_assignment MCP tool, and it
runs only when the API's approval endpoint is called (i.e. after a human clicks
Approve on the dashboard). ``change_crew`` edits the proposal in place and never
writes an assignment.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from backend.database import models
from backend.services.mcp_client import ASSIGNMENT_SERVER, run_tool
from backend.services.safety_rules import CREWS


class AssignmentError(Exception):
    """Raised when an approval cannot be committed."""


def change_crew(db: Session, work_order_id: int, crew: str) -> models.Proposal:
    """Update the proposed crew for a work order. Does NOT assign."""
    if crew not in CREWS:
        raise AssignmentError(f"Unknown crew '{crew}'")

    proposal = (
        db.query(models.Proposal)
        .filter(models.Proposal.work_order_id == work_order_id)
        .first()
    )
    if proposal is None:
        raise AssignmentError(f"No proposal for work order {work_order_id}")
    if proposal.work_order.status == models.STATUS_ASSIGNED:
        raise AssignmentError("Work order is already assigned")

    proposal.proposed_crew = crew
    db.commit()
    db.refresh(proposal)
    return proposal


def reject(
    db: Session,
    work_order_id: int,
    rejected_by: str,
    reason: str | None = None,
) -> models.WorkOrder:
    """Reject a proposal. Marks the work order rejected; writes no assignment."""
    proposal = (
        db.query(models.Proposal)
        .filter(models.Proposal.work_order_id == work_order_id)
        .first()
    )
    if proposal is None:
        raise AssignmentError(f"No proposal for work order {work_order_id}")
    work_order = proposal.work_order
    if work_order.status == models.STATUS_ASSIGNED:
        raise AssignmentError("Work order is already assigned")

    work_order.status = models.STATUS_REJECTED
    work_order.rejected_by = rejected_by
    work_order.rejected_reason = reason
    work_order.rejected_at = datetime.utcnow()
    db.commit()
    db.refresh(work_order)
    return work_order


def approve(
    db: Session,
    work_order_id: int,
    approved_by: str,
    crew_override: str | None = None,
) -> models.Assignment:
    """Commit an assignment via the write_assignment MCP tool (after approval)."""
    proposal = (
        db.query(models.Proposal)
        .filter(models.Proposal.work_order_id == work_order_id)
        .first()
    )
    if proposal is None:
        raise AssignmentError(f"No proposal for work order {work_order_id}")
    if proposal.work_order.status == models.STATUS_ASSIGNED:
        raise AssignmentError("Work order is already assigned")

    crew = crew_override or proposal.proposed_crew
    if crew not in CREWS:
        raise AssignmentError(f"Unknown crew '{crew}'")

    # This is the only call site of the write MCP tool in the whole system.
    result = run_tool(
        ASSIGNMENT_SERVER,
        "write_assignment",
        {
            "work_order_id": work_order_id,
            "crew": crew,
            "urgency": proposal.proposed_urgency,
            "is_safety_critical": proposal.is_safety_critical,
            "approved_by": approved_by,
        },
    )
    if not result.get("ok"):
        raise AssignmentError(result.get("error", "write_assignment failed"))

    # Reflect the committed state locally (the MCP server updated the DB rows).
    db.expire_all()
    return db.get(models.Assignment, result["assignment_id"])
