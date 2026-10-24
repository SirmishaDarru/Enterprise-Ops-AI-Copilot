"""Durable PostgreSQL queue, typed tools, exact approval, and transactional simulation."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.models import ServiceMembership, User
from app.incidents.models import Incident
from app.telemetry.models import LogEvent, MetricSample
from app.workflows.models import Workflow, WorkflowApproval, WorkflowEffect, WorkflowEvent

LEASE_SECONDS = 30
MAX_ATTEMPTS = 3
ACTION = 'simulate_pool_refresh'
TRANSITIONS = {
    'queued': {'running', 'cancelled', 'failed'},
    'running': {'queued', 'awaiting_approval', 'completed', 'cancelled', 'failed'},
    'awaiting_approval': {'queued', 'cancelled'},
    'completed': set(), 'failed': set(), 'cancelled': set(),
}


def move(row: Workflow, target: str) -> None:
    if target not in TRANSITIONS[row.state]:
        raise ValueError(f'Invalid workflow transition {row.state} -> {target}')
    row.state = target


def plan_for(row: Workflow) -> dict:
    if row.action != ACTION:
        raise ValueError('Action is not allowlisted')
    return {'action': ACTION, 'service_id': str(row.service_id),
            'incident_id': str(row.incident_id), 'max_simulated_effects': 1,
            'description': 'Record one synthetic pool refresh outcome in this local database. No service is contacted.'}


def fingerprint(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def event(db: Session, row: Workflow, kind: str, detail: str, actor_id=None):
    db.add(WorkflowEvent(workflow_id=row.id, event_type=kind, detail=detail, actor_id=actor_id))


def approval_for(db: Session, row: Workflow) -> WorkflowApproval | None:
    return db.scalar(select(WorkflowApproval).where(WorkflowApproval.workflow_id == row.id))


def snapshot_metrics(db: Session, service_id: uuid.UUID) -> list[dict]:
    """Read-only allowlisted tool; no arbitrary SQL or model-supplied arguments."""
    samples = db.scalars(select(MetricSample).where(MetricSample.service_id == service_id)
        .order_by(MetricSample.observed_at.desc()).limit(10)).all()
    return [{'sample_id': str(s.id), 'at': s.observed_at.isoformat(),
             'errors': s.error_count, 'requests': s.request_count,
             'p95_ms': s.latency_p95_ms} for s in samples]


def inspect_recent_logs(db: Session, service_id: uuid.UUID) -> list[dict]:
    logs = db.scalars(select(LogEvent).where(LogEvent.service_id == service_id)
        .order_by(LogEvent.occurred_at.desc()).limit(10)).all()
    return [{'log_id': str(item.id), 'at': item.occurred_at.isoformat(),
             'level': item.level, 'message': item.message} for item in logs]


def actor_has_scope(db: Session, row: Workflow, actor: User | None) -> bool:
    if actor is None or not actor.is_active or actor.role not in ('responder', 'approver', 'admin'):
        return False
    if actor.role == 'admin':
        return True
    return db.scalar(select(ServiceMembership.id).where(
        ServiceMembership.user_id == actor.id,
        ServiceMembership.service_id == row.service_id)) is not None


def release(row: Workflow):
    row.lease_token = None
    row.lease_until = None


def claim(db: Session, workflow_id: uuid.UUID | None = None) -> tuple[uuid.UUID, uuid.UUID] | None:
    """One consumer takes a due job or an expired lease with SKIP LOCKED."""
    now = datetime.now(timezone.utc)
    query = select(Workflow).where(or_(
        and_(Workflow.state == 'queued', Workflow.next_attempt_at <= now),
        and_(Workflow.state == 'running', Workflow.lease_until <= now)))
    if workflow_id is not None:
        query = query.where(Workflow.id == workflow_id)
    row = db.scalar(query.order_by(Workflow.created_at, Workflow.id)
                    .with_for_update(skip_locked=True).limit(1))
    if row is None:
        return None
    if row.attempts >= MAX_ATTEMPTS:
        if row.cancel_requested:
            move(row, 'cancelled')
            event(db, row, 'cancelled', 'Cancellation applied after worker lease expired')
        else:
            move(row, 'failed')
            row.error_code = 'RETRY_EXHAUSTED'
            event(db, row, 'failed', 'Worker lease or retry limit exhausted')
        row.phase = 'done'
        release(row)
        db.commit()
        return None
    if row.state == 'queued':
        move(row, 'running')
    row.attempts += 1
    row.lease_token = uuid.uuid4()
    row.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    event(db, row, 'claimed', f'Attempt {row.attempts} started')
    result = row.id, row.lease_token
    db.commit()
    return result


def execute_claim(db: Session, workflow_id: uuid.UUID, token: uuid.UUID,
                  before_commit: Callable[[], None] | None = None) -> bool:
    """All effects and state changes commit together. A stale lease token does nothing."""
    db.execute(text("SET LOCAL statement_timeout = '10000ms'"))
    row = db.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
    if row is None or row.state != 'running' or row.lease_token != token:
        db.rollback()
        return False
    if row.cancel_requested:
        move(row, 'cancelled')
        row.phase = 'done'
        release(row)
        event(db, row, 'cancelled', 'Cancelled before simulated outcome')
        db.commit()
        return True
    requester = db.get(User, row.requester_id)
    if not actor_has_scope(db, row, requester) or db.get(Incident, row.incident_id) is None:
        move(row, 'failed')
        row.error_code = 'ACCESS_REVOKED'
        row.phase = 'done'
        release(row)
        event(db, row, 'failed', 'Requester access or incident unavailable')
        db.commit()
        return True
    if row.phase == 'diagnostics':
        metrics = snapshot_metrics(db, row.service_id)
        logs = inspect_recent_logs(db, row.service_id)
        row.diagnostics = {'metrics': metrics, 'logs': logs, 'synthetic': True}
        if not metrics:
            move(row, 'failed')
            row.error_code = 'NO_TELEMETRY'
            row.phase = 'done'
            event(db, row, 'failed', 'No metric samples for this service')
        else:
            plan = plan_for(row)
            db.add(WorkflowApproval(workflow_id=row.id, plan=plan,
                                    plan_hash=fingerprint(plan), decision='pending'))
            move(row, 'awaiting_approval')
            row.phase = 'simulation'
            event(db, row, 'approval_requested', 'Read-only diagnostics complete; exact plan awaits approval')
        release(row)
        db.commit()
        return True
    if row.phase != 'simulation':
        raise ValueError('Unknown workflow phase')
    approval = approval_for(db, row)
    approver = db.get(User, approval.approver_id) if approval and approval.approver_id else None
    if (approval is None or approval.decision != 'approved'
            or approval.plan != plan_for(row)
            or approval.plan_hash != fingerprint(approval.plan)
            or approver is None or approver.id == row.requester_id
            or approver.role not in ('approver', 'admin')
            or not actor_has_scope(db, row, approver)):
        move(row, 'failed')
        row.error_code = 'APPROVAL_INVALID'
        row.phase = 'done'
        release(row)
        event(db, row, 'failed', 'Exact approval is missing or no longer authorized')
        db.commit()
        return True
    # This is a local record only. The unique constraint fences duplicate delivery.
    effect_id = uuid.uuid4()
    outcome = {'simulated': True, 'message': 'Synthetic pool refresh recorded; no service contacted',
               'service_id': str(row.service_id)}
    db.execute(insert(WorkflowEffect).values(id=effect_id, workflow_id=row.id,
        action_key=ACTION, plan_hash=approval.plan_hash, outcome=outcome)
        .on_conflict_do_nothing(index_elements=['workflow_id', 'action_key']))
    effect = db.scalar(select(WorkflowEffect).where(WorkflowEffect.workflow_id == row.id,
                                                   WorkflowEffect.action_key == ACTION))
    if effect.plan_hash != approval.plan_hash:
        raise ValueError('Effect plan hash mismatch')
    row.result = {'effect_id': str(effect.id), **effect.outcome}
    move(row, 'completed')
    row.phase = 'done'
    release(row)
    event(db, row, 'completed', 'One simulated outcome committed')
    record(db, actor_id=approval.approver_id, action='workflow.simulated_effect',
           target_type='workflow', target_id=str(row.id), outcome='allowed',
           request_id=str(token), context={'plan_hash': approval.plan_hash, 'simulated': True})
    if before_commit:
        before_commit()  # integration test can crash here and prove rollback/retry
    db.commit()
    return True


def retry_after_error(db: Session, workflow_id: uuid.UUID, token: uuid.UUID) -> None:
    row = db.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
    if row is None or row.state != 'running' or row.lease_token != token:
        db.rollback()
        return
    if row.cancel_requested:
        move(row, 'cancelled')
        row.phase = 'done'
        event(db, row, 'cancelled', 'Cancellation applied after step failure')
    elif row.attempts >= MAX_ATTEMPTS:
        move(row, 'failed')
        row.phase = 'done'
        row.error_code = 'RETRY_EXHAUSTED'
        event(db, row, 'failed', 'Step failed after retry limit')
    else:
        move(row, 'queued')
        row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=min(2 ** row.attempts, 30))
        row.error_code = 'STEP_RETRY'
        event(db, row, 'retry', 'Step failed; retry scheduled with backoff')
    release(row)
    db.commit()
