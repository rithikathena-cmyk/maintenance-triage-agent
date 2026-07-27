"""Pydantic request/response models for the API."""
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from backend.database.models import Proposal


class WorkOrderCreate(BaseModel):
    title: str
    description: str
    location: str | None = None
    reported_by: str | None = None


class WorkOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    location: str | None
    reported_by: str | None
    status: str
    created_at: datetime
    rejected_by: str | None = None
    rejected_reason: str | None = None
    rejected_at: datetime | None = None


class ProposalOut(BaseModel):
    """A work order joined with its (proposed) triage — the dashboard row."""

    work_order_id: int
    title: str
    description: str
    location: str | None
    reported_by: str | None
    status: str
    proposed_urgency: str
    proposed_crew: str
    is_safety_critical: bool
    safety_keywords: list[str]
    reasoning: str | None
    confidence: float | None
    source: str
    created_at: datetime


def proposal_out(p: "Proposal") -> ProposalOut:
    """Build a ``ProposalOut`` from an ORM ``Proposal`` (joined with its work order)."""
    wo = p.work_order
    keywords = [k.strip() for k in (p.safety_keywords or "").split(",") if k.strip()]
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
        safety_keywords=keywords,
        reasoning=p.reasoning,
        confidence=p.confidence,
        source=p.source,
        created_at=wo.created_at,
    )


class TriageSummary(BaseModel):
    triaged: int          # orders triaged in this call
    queue_size: int       # orders this call attempted
    remaining: int = 0    # pending orders still awaiting triage after this call
    busy: bool = False    # True if another triage run held the lock (no work done)


class QueueStats(BaseModel):
    """Counts backing the dashboard KPI tiles."""

    open_orders: int      # filed but not yet resolved (pending + triaged)
    safety_cases: int     # safety-critical proposals awaiting review
    awaiting_review: int   # triaged, pending a dispatcher decision
    assigned: int         # assignments committed
    rejected: int         # proposals a dispatcher rejected
    pending_triage: int   # filed but not yet run through the agent


class ChangeCrewRequest(BaseModel):
    crew: str


class RejectRequest(BaseModel):
    rejected_by: str
    reason: str | None = None


class ApproveRequest(BaseModel):
    approved_by: str
    crew: str | None = None  # optional override; defaults to the proposed crew


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    crew: str
    urgency: str
    is_safety_critical: bool
    approved_by: str
    approved_at: datetime
