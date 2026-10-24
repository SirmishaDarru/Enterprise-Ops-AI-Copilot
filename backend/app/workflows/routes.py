import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.models import User
from app.auth.security import current_user, require_roles
from app.core.access import permitted_service_ids, require_service
from app.core.db import get_db
from app.core.errors import ApiError
from app.incidents.models import Incident
from app.workflows.models import Workflow, WorkflowApproval, WorkflowEvent
from app.workflows.service import ACTION, event, move

router = APIRouter(prefix='/workflows', tags=['workflows'])
DB = Annotated[Session, Depends(get_db)]
USER = Annotated[User, Depends(current_user)]
RUNNER = Annotated[User, Depends(require_roles('responder', 'approver', 'admin'))]
APPROVER = Annotated[User, Depends(require_roles('approver', 'admin'))]


class CreateWorkflow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['simulate_pool_refresh']


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approval_id: uuid.UUID
    plan_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    decision: Literal['approved', 'rejected']


def accessible(db: Session, user: User, workflow_id: uuid.UUID, lock=False) -> Workflow:
    stmt = select(Workflow).where(Workflow.id == workflow_id)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise ApiError(404, 'NOT_FOUND', 'Workflow not found')
    require_service(db, user, row.service_id)
    if user.id != row.requester_id and user.role not in ('approver', 'admin'):
        raise ApiError(404, 'NOT_FOUND', 'Workflow not found')
    return row


def output(db: Session, row: Workflow, detailed=False):
    value = {'id': str(row.id), 'incident_id': str(row.incident_id),
             'service_id': str(row.service_id), 'requester_id': str(row.requester_id),
             'action': row.action, 'state': row.state, 'phase': row.phase,
             'attempts': row.attempts, 'error_code': row.error_code,
             'cancel_requested': row.cancel_requested,
             'created_at': row.created_at.isoformat() if row.created_at else None}
    if detailed:
        approval = db.scalar(select(WorkflowApproval).where(WorkflowApproval.workflow_id == row.id))
        value['approval'] = ({'id': str(approval.id), 'plan': approval.plan,
            'plan_hash': approval.plan_hash, 'decision': approval.decision,
            'approver_id': str(approval.approver_id) if approval.approver_id else None}
            if approval else None)
        value['diagnostics'] = row.diagnostics
        value['result'] = row.result
        events = db.scalars(select(WorkflowEvent).where(WorkflowEvent.workflow_id == row.id)
                            .order_by(WorkflowEvent.created_at, WorkflowEvent.id).limit(100)).all()
        value['events'] = [{'id': str(item.id), 'type': item.event_type, 'detail': item.detail,
                            'at': item.created_at.isoformat()} for item in events]
    return value


@router.post('/incidents/{incident_id}', status_code=201)
def create_workflow(incident_id: uuid.UUID, body: CreateWorkflow, db: DB, request: Request,
                    user: RUNNER, idempotency_key: Annotated[uuid.UUID, Header(alias='Idempotency-Key')]):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, 'NOT_FOUND', 'Incident not found')
    require_service(db, user, incident.service_id)
    identifier = uuid.uuid4()
    created = db.scalar(insert(Workflow).values(id=identifier, incident_id=incident.id,
        service_id=incident.service_id, requester_id=user.id,
        idempotency_key=idempotency_key, action=body.action, state='queued',
        phase='diagnostics', attempts=0, cancel_requested=False,
        next_attempt_at=datetime.now(timezone.utc)).on_conflict_do_nothing(
        index_elements=['requester_id', 'idempotency_key']).returning(Workflow.id))
    if created is None:
        row = db.scalar(select(Workflow).where(Workflow.requester_id == user.id,
            Workflow.idempotency_key == idempotency_key))
        if row.incident_id != incident_id or row.action != body.action:
            raise ApiError(409, 'IDEMPOTENCY_CONFLICT', 'Key was used with another request')
    else:
        row = db.get(Workflow, created)
        event(db, row, 'created', 'Read-only diagnostics queued', user.id)
        record(db, actor_id=user.id, action='workflow.create', target_type='workflow',
               target_id=str(row.id), outcome='allowed', request_id=request.state.request_id,
               context={'incident_id': str(incident_id), 'action': ACTION})
    db.commit()
    return output(db, row, detailed=True)


@router.get('')
def mine(db: DB, user: USER):
    rows = db.scalars(select(Workflow).where(Workflow.requester_id == user.id)
        .order_by(Workflow.created_at.desc(), Workflow.id.desc()).limit(50)).all()
    return {'items': [output(db, row) for row in rows]}


@router.get('/pending')
def pending(db: DB, user: APPROVER):
    stmt = select(Workflow).where(Workflow.state == 'awaiting_approval',
                                  Workflow.requester_id != user.id)
    scope = permitted_service_ids(db, user)
    if scope is not None:
        stmt = stmt.where(Workflow.service_id.in_(scope))
    rows = db.scalars(stmt.order_by(Workflow.created_at).limit(50)).all()
    return {'items': [output(db, row) for row in rows]}


@router.get('/{workflow_id}')
def detail(workflow_id: uuid.UUID, db: DB, user: USER):
    return output(db, accessible(db, user, workflow_id), detailed=True)


@router.post('/{workflow_id}/decision')
def decide(workflow_id: uuid.UUID, body: Decision, db: DB, request: Request, user: APPROVER):
    row = accessible(db, user, workflow_id, lock=True)
    if row.requester_id == user.id:
        raise ApiError(403, 'SELF_APPROVAL', 'A different approver is required')
    approval = db.scalar(select(WorkflowApproval).where(WorkflowApproval.workflow_id == row.id))
    if approval is None or approval.id != body.approval_id or approval.plan_hash != body.plan_hash:
        raise ApiError(409, 'APPROVAL_MISMATCH', 'Approval ID or exact plan hash differs')
    if approval.decision != 'pending':
        if approval.decision != body.decision or approval.approver_id != user.id:
            raise ApiError(409, 'DECISION_CONFLICT', 'Approval already decided')
        return output(db, row, detailed=True)
    if row.state != 'awaiting_approval':
        raise ApiError(409, 'STATE_CONFLICT', 'Workflow is no longer awaiting approval')
    approval.decision = body.decision
    approval.approver_id = user.id
    approval.decided_at = datetime.now(timezone.utc)
    if body.decision == 'approved':
        move(row, 'queued')
        row.next_attempt_at = datetime.now(timezone.utc)
        event(db, row, 'approved', 'Exact plan approved; simulated step queued', user.id)
    else:
        move(row, 'cancelled')
        row.phase = 'done'
        event(db, row, 'rejected', 'Plan rejected; no simulated outcome', user.id)
    record(db, actor_id=user.id, action='workflow.decision', target_type='workflow',
           target_id=str(row.id), outcome=body.decision, request_id=request.state.request_id,
           context={'plan_hash': approval.plan_hash, 'approval_id': str(approval.id)})
    db.commit()
    return output(db, row, detailed=True)


@router.post('/{workflow_id}/cancel')
def cancel(workflow_id: uuid.UUID, db: DB, request: Request, user: RUNNER):
    row = accessible(db, user, workflow_id, lock=True)
    if row.requester_id != user.id:
        raise ApiError(403, 'FORBIDDEN', 'Only the requester may cancel')
    if row.state in ('completed', 'failed', 'cancelled'):
        raise ApiError(409, 'STATE_CONFLICT', 'Workflow already finished')
    if row.state == 'running':
        row.cancel_requested = True
        event(db, row, 'cancel_requested', 'Cancellation requested while worker owns lease', user.id)
    else:
        if row.state == 'awaiting_approval':
            approval = db.scalar(select(WorkflowApproval).where(WorkflowApproval.workflow_id == row.id))
            if approval and approval.decision == 'pending':
                approval.decision = 'cancelled'
        move(row, 'cancelled')
        row.phase = 'done'
        event(db, row, 'cancelled', 'Cancelled before simulated outcome', user.id)
    record(db, actor_id=user.id, action='workflow.cancel', target_type='workflow',
           target_id=str(row.id), outcome='allowed', request_id=request.state.request_id)
    db.commit()
    return output(db, row, detailed=True)
