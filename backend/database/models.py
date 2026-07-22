"""ORM models for the maintenance triage system.

Three tables mirror the architecture:

* ``work_orders``  — the incoming queue an operator files into.
* ``proposals``    — the Claude agent's *proposed* triage (never an assignment).
* ``assignments``  — written ONLY when a human clicks Approve.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database.database import Base

# Work order lifecycle
STATUS_PENDING = "pending"    # filed, not yet triaged
STATUS_TRIAGED = "triaged"    # agent has proposed urgency + crew, awaiting approval
STATUS_ASSIGNED = "assigned"  # human approved, assignment written
STATUS_REJECTED = "rejected"  # human rejected the proposal; no assignment written


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(200), nullable=True)
    reported_by = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default=STATUS_PENDING, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Set when a dispatcher rejects the agent's proposal (no assignment written).
    rejected_by = Column(String(120), nullable=True)
    rejected_reason = Column(Text, nullable=True)
    rejected_at = Column(DateTime, nullable=True)

    proposal = relationship(
        "Proposal",
        back_populates="work_order",
        uselist=False,
        cascade="all, delete-orphan",
    )
    assignment = relationship(
        "Assignment",
        back_populates="work_order",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Proposal(Base):
    """The agent's proposed triage. Editable (Change Crew) until approved."""

    __tablename__ = "proposals"
    __table_args__ = (UniqueConstraint("work_order_id", name="uq_proposal_work_order"),)

    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    proposed_urgency = Column(String(20), nullable=False)
    proposed_crew = Column(String(80), nullable=False)
    is_safety_critical = Column(Boolean, nullable=False, default=False)
    safety_keywords = Column(Text, nullable=True)  # comma-separated matches
    reasoning = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)  # model's 0..1 confidence in its call
    source = Column(String(40), nullable=False, default="claude")  # claude | heuristic
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    work_order = relationship("WorkOrder", back_populates="proposal")


class Assignment(Base):
    """A committed crew assignment. Only ever created via human approval."""

    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("work_order_id", name="uq_assignment_work_order"),)

    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    crew = Column(String(80), nullable=False)
    urgency = Column(String(20), nullable=False)
    is_safety_critical = Column(Boolean, nullable=False, default=False)
    approved_by = Column(String(120), nullable=False)
    approved_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    work_order = relationship("WorkOrder", back_populates="assignment")
