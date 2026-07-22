"""Approval + assignment endpoints (the human-in-the-loop write side)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import models
from backend.database.database import get_db
from backend.schemas.schemas import (
    ApproveRequest,
    AssignmentOut,
    ChangeCrewRequest,
    ProposalOut,
    RejectRequest,
    WorkOrderOut,
)
from backend.services import assignment_service
from backend.services.assignment_service import AssignmentError

router = APIRouter(tags=["assignments"])


@router.post("/proposals/{work_order_id}/change-crew", response_model=ProposalOut)
def change_crew(
    work_order_id: int, payload: ChangeCrewRequest, db: Session = Depends(get_db)
):
    """Adjust the proposed crew. Does not write an assignment."""
    try:
        proposal = assignment_service.change_crew(db, work_order_id, payload.crew)
    except AssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    from backend.api.workorders import _to_proposal_out

    return _to_proposal_out(proposal)


@router.post("/proposals/{work_order_id}/reject", response_model=WorkOrderOut)
def reject_proposal(
    work_order_id: int, payload: RejectRequest, db: Session = Depends(get_db)
):
    """Reject a proposal. Marks the work order rejected; writes no assignment."""
    try:
        work_order = assignment_service.reject(
            db, work_order_id, rejected_by=payload.rejected_by, reason=payload.reason
        )
    except AssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return work_order


@router.post("/assignments/approve", response_model=AssignmentOut, status_code=201)
def approve_assignment(payload: ApproveRequest, work_order_id: int, db: Session = Depends(get_db)):
    """Approve a proposal — the only path that writes an assignment.

    Invoked when a dispatcher clicks Approve. Routes through the
    write_assignment MCP tool.
    """
    try:
        assignment = assignment_service.approve(
            db,
            work_order_id=work_order_id,
            approved_by=payload.approved_by,
            crew_override=payload.crew,
        )
    except AssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return assignment


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(db: Session = Depends(get_db)):
    """Assignment history, most recent first."""
    return (
        db.query(models.Assignment)
        .order_by(models.Assignment.approved_at.desc())
        .all()
    )
