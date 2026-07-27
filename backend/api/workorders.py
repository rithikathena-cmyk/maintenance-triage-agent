"""Work-order and proposal endpoints (the operator + read side of triage)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import models
from backend.database.database import get_db
from backend.schemas.schemas import (
    ProposalOut,
    QueueStats,
    TriageSummary,
    WorkOrderCreate,
    WorkOrderOut,
    proposal_out,
)
from backend.services import triage_service
from backend.services.safety_rules import urgency_rank

router = APIRouter(tags=["work-orders"])


@router.post("/work-orders", response_model=WorkOrderOut, status_code=201)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db)):
    """Operator files a maintenance request; auto-triaged best-effort on the spot."""
    work_order = models.WorkOrder(
        title=payload.title,
        description=payload.description,
        location=payload.location,
        reported_by=payload.reported_by,
        status=models.STATUS_PENDING,
    )
    db.add(work_order)
    db.commit()
    db.refresh(work_order)

    triage_service.triage_work_order(db, work_order)
    db.refresh(work_order)
    return work_order


@router.get("/work-orders", response_model=list[WorkOrderOut])
def list_work_orders(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.WorkOrder)
    if status:
        query = query.filter(models.WorkOrder.status == status)
    return query.order_by(models.WorkOrder.created_at.asc()).all()


@router.post("/triage", response_model=TriageSummary)
def run_triage(rescan: bool = False, limit: int | None = None, db: Session = Depends(get_db)):
    """Triage pending work orders and store proposals (chunked via ``limit``)."""
    return triage_service.run_triage(db, rescan=rescan, limit=limit)


@router.get("/stats", response_model=QueueStats)
def stats(db: Session = Depends(get_db)):
    """Aggregate counts backing the dashboard KPI tiles."""
    WO = models.WorkOrder

    def wo_count(status: str) -> int:
        return db.query(WO).filter(WO.status == status).count()

    pending = wo_count(models.STATUS_PENDING)
    awaiting = wo_count(models.STATUS_TRIAGED)
    safety_cases = (
        db.query(models.Proposal)
        .join(WO)
        .filter(WO.status == models.STATUS_TRIAGED, models.Proposal.is_safety_critical.is_(True))
        .count()
    )
    return QueueStats(
        open_orders=pending + awaiting,
        safety_cases=safety_cases,
        awaiting_review=awaiting,
        assigned=wo_count(models.STATUS_ASSIGNED),
        rejected=wo_count(models.STATUS_REJECTED),
        pending_triage=pending,
    )


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(db: Session = Depends(get_db)):
    """Proposals awaiting review, safety-critical first."""
    rows = (
        db.query(models.Proposal)
        .join(models.WorkOrder)
        .filter(models.WorkOrder.status == models.STATUS_TRIAGED)
        .all()
    )
    # Safety-critical first, then by urgency, then oldest first — safety
    # keyword hits must always surface at the top of the queue.
    rows.sort(
        key=lambda p: (
            0 if p.is_safety_critical else 1,
            urgency_rank(p.proposed_urgency),
            p.work_order.created_at,
        )
    )
    return [proposal_out(p) for p in rows]


@router.get("/proposals/{work_order_id}", response_model=ProposalOut)
def get_proposal(work_order_id: int, db: Session = Depends(get_db)):
    proposal = (
        db.query(models.Proposal)
        .filter(models.Proposal.work_order_id == work_order_id)
        .first()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal_out(proposal)
