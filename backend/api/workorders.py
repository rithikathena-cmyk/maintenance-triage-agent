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
)
from backend.services import triage_service
from backend.services.safety_rules import urgency_rank

router = APIRouter(tags=["work-orders"])


@router.post("/work-orders", response_model=WorkOrderOut, status_code=201)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db)):
    """Operator files a maintenance request into the queue.

    Auto-triage: the order is immediately classified by Claude so it lands in
    the dispatcher's queue already triaged. This is best-effort — if triage
    fails the order stays ``pending`` and the filing still succeeds.
    """
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
def run_triage(
    rescan: bool = False,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """Run the Claude agent over pending work orders and store proposals.

    Pass ``rescan=true`` to also re-triage orders already awaiting review
    (never touches assigned or rejected orders). Pass ``limit`` to process at
    most that many orders this call — the frontend chunks the run for progress.
    """
    return triage_service.run_triage(db, rescan=rescan, limit=limit)


@router.get("/stats", response_model=QueueStats)
def stats(db: Session = Depends(get_db)):
    """Aggregate counts backing the dashboard KPI tiles."""
    WO = models.WorkOrder

    def wo_count(status: str) -> int:
        return db.query(WO).filter(WO.status == status).count()

    pending = wo_count(models.STATUS_PENDING)
    awaiting = wo_count(models.STATUS_TRIAGED)
    assigned = wo_count(models.STATUS_ASSIGNED)
    rejected = wo_count(models.STATUS_REJECTED)
    safety_cases = (
        db.query(models.Proposal)
        .join(WO)
        .filter(WO.status == models.STATUS_TRIAGED)
        .filter(models.Proposal.is_safety_critical.is_(True))
        .count()
    )
    return QueueStats(
        open_orders=pending + awaiting,
        safety_cases=safety_cases,
        awaiting_review=awaiting,
        assigned=assigned,
        rejected=rejected,
        pending_triage=pending,
    )


def _to_proposal_out(proposal: models.Proposal) -> ProposalOut:
    wo = proposal.work_order
    keywords = (
        [k.strip() for k in proposal.safety_keywords.split(",") if k.strip()]
        if proposal.safety_keywords
        else []
    )
    return ProposalOut(
        work_order_id=wo.id,
        title=wo.title,
        description=wo.description,
        location=wo.location,
        reported_by=wo.reported_by,
        status=wo.status,
        proposed_urgency=proposal.proposed_urgency,
        proposed_crew=proposal.proposed_crew,
        is_safety_critical=proposal.is_safety_critical,
        safety_keywords=keywords,
        reasoning=proposal.reasoning,
        confidence=proposal.confidence,
        source=proposal.source,
        created_at=wo.created_at,
    )


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(include_assigned: bool = False, db: Session = Depends(get_db)):
    """Proposals awaiting review, safety-critical first.

    Sort order: safety-critical rows first, then by urgency rank, then oldest
    first — which is exactly the 'safety keywords surface at the top' criterion.
    """
    query = db.query(models.Proposal).join(models.WorkOrder)
    if not include_assigned:
        query = query.filter(models.WorkOrder.status == models.STATUS_TRIAGED)

    proposals = query.all()
    proposals.sort(
        key=lambda p: (
            0 if p.is_safety_critical else 1,
            urgency_rank(p.proposed_urgency),
            p.work_order.created_at,
        )
    )
    return [_to_proposal_out(p) for p in proposals]


@router.get("/proposals/{work_order_id}", response_model=ProposalOut)
def get_proposal(work_order_id: int, db: Session = Depends(get_db)):
    proposal = (
        db.query(models.Proposal)
        .filter(models.Proposal.work_order_id == work_order_id)
        .first()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _to_proposal_out(proposal)
