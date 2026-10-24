import uuid
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.models import User
from app.auth.security import current_user, require_roles
from app.core.access import require_service
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.investigation.evidence import collect
from app.investigation.models import Investigation
from app.investigation.provider import Completion, ProviderFailure, configured_provider, cost
from app.investigation.service import validate_report
from app.incidents.models import Incident
from app.knowledge.routes import source as knowledge_source

router = APIRouter(prefix='/investigations', tags=['investigations'])
DB = Annotated[Session, Depends(get_db)]
USER = Annotated[User, Depends(current_user)]
RUNNER = Annotated[User, Depends(require_roles('responder', 'approver', 'admin'))]


def visible_run(db: Session, user: User, investigation_id: uuid.UUID) -> Investigation:
    run = db.scalar(select(Investigation).where(Investigation.id == investigation_id,
                                               Investigation.actor_id == user.id))
    if run is None:
        raise ApiError(404, 'NOT_FOUND', 'Investigation not found')
    incident = db.get(Incident, run.incident_id)
    if incident is None:
        raise ApiError(404, 'NOT_FOUND', 'Investigation not found')
    require_service(db, user, incident.service_id)
    return run


def output(run: Investigation, include_report: bool = False) -> dict:
    result = {'id': str(run.id), 'incident_id': str(run.incident_id), 'status': run.status,
              'provider': run.provider, 'model': run.model, 'error_code': run.error_code,
              'input_tokens': run.input_tokens, 'output_tokens': run.output_tokens,
              'cost_usd': run.cost_usd, 'latency_ms': run.latency_ms,
              'created_at': run.created_at.isoformat() if run.created_at else None}
    if include_report:
        result['report'] = run.report
        result['evidence'] = run.evidence
    return result


@router.post('/incidents/{incident_id}', status_code=201)
def investigate(incident_id: uuid.UUID, db: DB, request: Request, user: RUNNER):
    settings = get_settings()
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, 'NOT_FOUND', 'Incident not found')
    require_service(db, user, incident.service_id)
    count = db.scalar(select(func.count()).select_from(Investigation).where(
        Investigation.actor_id == user.id,
        Investigation.created_at >= datetime.now(timezone.utc) - timedelta(hours=1)))
    if count >= 10:
        raise ApiError(429, 'RATE_LIMITED', 'Limit of 10 investigations per hour')
    start = perf_counter()
    incident, evidence, gaps = collect(db, user, incident_id)
    provider = configured_provider(settings)
    status, report, error, usage = 'insufficient', None, None, None
    if not any(item['kind'] == 'alert' for item in evidence):
        error = 'INSUFFICIENT_EVIDENCE'
    else:
        try:
            usage = provider.generate(evidence, gaps)
            report = validate_report(usage.data, evidence, gaps)
            status = 'completed'
        except ProviderFailure as failure:
            status, error = 'failed', failure.code
            if failure.input_tokens is not None or failure.output_tokens is not None:
                usage = Completion({}, failure.input_tokens, failure.output_tokens)
    run = Investigation(incident_id=incident.id, actor_id=user.id, status=status,
        provider=provider.name, model=provider.model, evidence=evidence, report=report,
        error_code=error, input_tokens=usage.input_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
        cost_usd=cost(settings, usage) if usage else None,
        latency_ms=int((perf_counter() - start) * 1000))
    db.add(run)
    db.flush()
    record(db, actor_id=user.id, action='investigation.create', target_type='investigation',
           target_id=str(run.id), outcome=status, request_id=request.state.request_id,
           context={'incident_id': str(incident_id), 'provider': provider.name,
                    'error_code': error, 'latency_ms': run.latency_ms})
    db.commit()
    db.refresh(run)
    return output(run, include_report=True)


@router.get('/incidents/{incident_id}')
def list_investigations(incident_id: uuid.UUID, db: DB, user: USER):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, 'NOT_FOUND', 'Incident not found')
    require_service(db, user, incident.service_id)
    rows = db.scalars(select(Investigation).where(Investigation.incident_id == incident_id,
        Investigation.actor_id == user.id).order_by(
        Investigation.created_at.desc(), Investigation.id.desc()).limit(30)).all()
    return {'items': [output(row) for row in rows]}


@router.get('/{investigation_id}')
def get_investigation(investigation_id: uuid.UUID, db: DB, user: USER):
    run = visible_run(db, user, investigation_id)
    # Reports can include private document text; revoke the entire snapshot if any source
    # passage was removed or its current grant no longer permits this actor.
    for item in run.evidence:
        if item['kind'] == 'source':
            try:
                knowledge_source(uuid.UUID(item['id'].split(':', 1)[1]), db, user)
            except ApiError:
                raise ApiError(404, 'NOT_FOUND', 'Investigation evidence no longer available') from None
    return output(run, include_report=True)
