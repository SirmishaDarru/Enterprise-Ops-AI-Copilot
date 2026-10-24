import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
                        String, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Workflow(Base):
    __tablename__ = 'workflows'
    __table_args__ = (
        UniqueConstraint('requester_id', 'idempotency_key'),
        CheckConstraint("state IN ('queued','running','awaiting_approval','completed','failed','cancelled')", name='ck_workflow_state'),
        CheckConstraint("phase IN ('diagnostics','simulation','done')", name='ck_workflow_phase'),
        Index('ix_workflow_queue', 'state', 'next_attempt_at', 'lease_until'),
        Index('ix_workflow_requester', 'requester_id', 'created_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('services.id', ondelete='CASCADE'), nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(25), nullable=False, default='queued')
    phase: Mapped[str] = mapped_column(String(25), nullable=False, default='diagnostics')
    diagnostics: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkflowApproval(Base):
    __tablename__ = 'workflow_approvals'
    __table_args__ = (UniqueConstraint('workflow_id'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False)
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False, default='pending')
    approver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkflowEffect(Base):
    """Only simulated consequences; unique key is the effect idempotency fence."""
    __tablename__ = 'workflow_effects'
    __table_args__ = (UniqueConstraint('workflow_id', 'action_key'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False)
    action_key: Mapped[str] = mapped_column(String(40), nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkflowEvent(Base):
    __tablename__ = 'workflow_events'
    __table_args__ = (Index('ix_workflow_event_order', 'workflow_id', 'created_at', 'id'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(String(300), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
