import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.models import User
from app.auth.security import current_user, require_roles
from app.core.access import permitted_service_ids, require_service
from app.core.db import get_db
from app.core.paging import after_cursor, page
from app.incidents.models import AlertRule
from app.incidents.service import evaluate
from app.telemetry.demo import seed_demo
from app.telemetry.models import (DeploymentEvent, LogEvent, MetricSample, Service,
                                  ServiceDependency)

router = APIRouter(tags=["telemetry"])


def metric_out(sample: MetricSample) -> dict:
    return {"id": str(sample.id), "service_id": str(sample.service_id),
            "observed_at": sample.observed_at, "request_count": sample.request_count,
            "error_count": sample.error_count, "error_rate_percent": round(
                100 * sample.error_count / sample.request_count, 1) if sample.request_count else 0,
            "latency_p95_ms": sample.latency_p95_ms, "source": sample.source}


def log_out(log: LogEvent) -> dict:
    return {"id": str(log.id), "service_id": str(log.service_id),
            "occurred_at": log.occurred_at, "level": log.level, "message": log.message,
            "source": log.source}


@router.get("/services")
def services(db: Annotated[Session, Depends(get_db)],
             user: Annotated[User, Depends(current_user)]):
    query = select(Service).order_by(Service.name)
    scope = permitted_service_ids(db, user)
    if scope is not None:
        query = query.where(Service.id.in_(scope))
    records = db.scalars(query).all()
    allowed = {service.id for service in records}
    edges = db.scalars(select(ServiceDependency)).all()
    return {"items": [{"id": str(s.id), "name": s.name, "description": s.description,
                       "depends_on": [str(e.depends_on_id) for e in edges
                                      if e.service_id == s.id and e.depends_on_id in allowed]}
                      for s in records]}


@router.get("/telemetry/metrics")
def metrics(service_id: uuid.UUID, db: Annotated[Session, Depends(get_db)],
            user: Annotated[User, Depends(current_user)], limit: int = Query(60, ge=1, le=500)):
    require_service(db, user, service_id)
    rows = db.scalars(select(MetricSample).where(MetricSample.service_id == service_id)
                      .order_by(MetricSample.observed_at.desc()).limit(limit)).all()
    return {"items": [metric_out(m) for m in reversed(rows)]}


@router.get("/telemetry/logs")
def logs(service_id: uuid.UUID, db: Annotated[Session, Depends(get_db)],
         user: Annotated[User, Depends(current_user)], q: str | None = Query(None, max_length=100),
         level: str | None = Query(None, pattern="^(INFO|WARN|ERROR)$"),
         cursor: str | None = None, limit: int = Query(30, ge=1, le=100)):
    require_service(db, user, service_id)
    query = select(LogEvent).where(LogEvent.service_id == service_id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(LogEvent.message.ilike(f"%{escaped}%", escape="\\"))
    if level:
        query = query.where(LogEvent.level == level)
    boundary = after_cursor(LogEvent.occurred_at, LogEvent.id, cursor)
    if boundary is not None:
        query = query.where(boundary)
    rows = db.scalars(query.order_by(LogEvent.occurred_at.desc(), LogEvent.id.desc())
                      .limit(limit + 1)).all()
    selected, next_cursor = page(rows, limit, "occurred_at")
    return {"items": [log_out(row) for row in selected], "next_cursor": next_cursor}


@router.get("/telemetry/deployments")
def deployments(service_id: uuid.UUID, db: Annotated[Session, Depends(get_db)],
                user: Annotated[User, Depends(current_user)]):
    require_service(db, user, service_id)
    rows = db.scalars(select(DeploymentEvent).where(DeploymentEvent.service_id == service_id)
                      .order_by(DeploymentEvent.occurred_at.desc()).limit(30)).all()
    return {"items": [{"id": str(e.id), "occurred_at": e.occurred_at,
                       "version": e.version, "description": e.description, "source": e.source}
                      for e in rows]}


@router.post("/demo/replay")
def replay(db: Annotated[Session, Depends(get_db)], request: Request,
           user: Annotated[User, Depends(require_roles("admin"))]):
    fixture = seed_demo(db)
    rule = db.get(AlertRule, fixture["rule_id"])
    incident_ids = set()
    for sample_id in fixture["sample_ids"]:
        incident_id = evaluate(db, rule, db.get(MetricSample, sample_id))
        if incident_id:
            incident_ids.add(str(incident_id))
    record(db, actor_id=user.id, action="demo.replay", target_type="service",
           target_id=str(fixture["service_id"]), outcome="allowed",
           request_id=request.state.request_id, context={"synthetic": True})
    db.commit()
    return {"synthetic": True, "service_id": str(fixture["service_id"]),
            "incident_ids": sorted(incident_ids), "message": "Deterministic demo replayed"}
