import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.models import User
from app.auth.security import current_user, require_roles
from app.core.access import permitted_service_ids, require_service
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.paging import after_cursor, page
from app.incidents.models import AlertEvent, AlertRule, Incident, IncidentEvent
from app.incidents.service import evaluate, transition
from app.telemetry.models import MetricSample, Service
from app.telemetry.routes import metric_out

router = APIRouter(tags=["incidents"])


def incident_out(row: Incident, service_name: str) -> dict:
    return {"id": str(row.id), "service_id": str(row.service_id), "service_name": service_name,
            "rule_id": str(row.rule_id), "title": row.title, "status": row.status,
            "severity": row.severity, "created_at": row.created_at, "updated_at": row.updated_at,
            "resolved_at": row.resolved_at, "synthetic": not service_name.startswith("live-checkout-demo")}


@router.get("/dashboard")
def dashboard(db: Annotated[Session, Depends(get_db)],
              user: Annotated[User, Depends(current_user)]):
    query = select(Service).order_by(Service.name)
    scope = permitted_service_ids(db, user)
    if scope is not None:
        query = query.where(Service.id.in_(scope))
    items = []
    for service in db.scalars(query):
        latest = db.scalar(select(MetricSample).where(MetricSample.service_id == service.id)
                           .order_by(MetricSample.observed_at.desc()).limit(1))
        active = db.scalar(select(func.count()).select_from(Incident).where(
            Incident.service_id == service.id, Incident.status.in_(("open", "investigating"))))
        items.append({"id": str(service.id), "name": service.name, "description": service.description,
                      "latest": metric_out(latest) if latest else None,
                      "active_incidents": active, "source": latest.source if latest else ("live_demo" if service.name == "live-checkout-demo" else "synthetic")})
    return {"services": items, "synthetic": False if any(item["source"] == "live_demo" for item in items) else True}


@router.get("/alerts/rules")
def rules(db: Annotated[Session, Depends(get_db)],
          user: Annotated[User, Depends(current_user)], service_id: uuid.UUID | None = None):
    query = select(AlertRule)
    scope = permitted_service_ids(db, user)
    if scope is not None:
        query = query.where(AlertRule.service_id.in_(scope))
    if service_id:
        require_service(db, user, service_id)
        query = query.where(AlertRule.service_id == service_id)
    rows = db.scalars(query.order_by(AlertRule.name)).all()
    return {"items": [{"id": str(r.id), "service_id": str(r.service_id), "name": r.name,
                       "threshold_percent": r.threshold_percent, "enabled": r.enabled} for r in rows]}


class RuleUpdate(BaseModel):
    threshold_percent: int = Field(ge=1, le=100)
    enabled: bool


@router.patch("/alerts/rules/{rule_id}")
def update_rule(rule_id: uuid.UUID, changes: RuleUpdate, db: Annotated[Session, Depends(get_db)],
                request: Request, user: Annotated[User, Depends(require_roles("admin"))]):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise ApiError(404, "NOT_FOUND", "Alert rule not found")
    rule.threshold_percent = changes.threshold_percent
    rule.enabled = changes.enabled
    record(db, actor_id=user.id, action="alert_rule.update", target_type="alert_rule",
           target_id=str(rule.id), outcome="allowed", request_id=request.state.request_id,
           context={"threshold_percent": changes.threshold_percent, "enabled": changes.enabled})
    db.commit()
    return {"id": str(rule.id), "threshold_percent": rule.threshold_percent, "enabled": rule.enabled}


@router.post("/alerts/rules/{rule_id}/evaluate")
def evaluate_rule(rule_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], request: Request,
                  user: Annotated[User, Depends(require_roles("responder", "approver", "admin"))]):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise ApiError(404, "NOT_FOUND", "Alert rule not found")
    require_service(db, user, rule.service_id)
    samples = db.scalars(select(MetricSample).where(MetricSample.service_id == rule.service_id)
                         .order_by(MetricSample.observed_at.desc()).limit(60)).all()
    matched = {str(identifier) for sample in reversed(samples)
               if (identifier := evaluate(db, rule, sample))}
    record(db, actor_id=user.id, action="alert_rule.evaluate", target_type="alert_rule",
           target_id=str(rule.id), outcome="allowed", request_id=request.state.request_id,
           context={"samples_checked": len(samples)})
    db.commit()
    return {"incident_ids": sorted(matched), "samples_checked": len(samples)}


@router.get("/incidents")
def incidents(db: Annotated[Session, Depends(get_db)],
              user: Annotated[User, Depends(current_user)],
              status: Literal["open", "investigating", "resolved"] | None = None,
              q: str | None = Query(None, max_length=100), service_id: uuid.UUID | None = None,
              cursor: str | None = None, limit: int = Query(30, ge=1, le=100)):
    query = select(Incident, Service.name).join(Service, Service.id == Incident.service_id)
    scope = permitted_service_ids(db, user)
    if scope is not None:
        query = query.where(Incident.service_id.in_(scope))
    if service_id:
        require_service(db, user, service_id)
        query = query.where(Incident.service_id == service_id)
    if status:
        query = query.where(Incident.status == status)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Incident.title.ilike(f"%{escaped}%", escape="\\"))
    boundary = after_cursor(Incident.created_at, Incident.id, cursor)
    if boundary is not None:
        query = query.where(boundary)
    rows = db.execute(query.order_by(Incident.created_at.desc(), Incident.id.desc())
                      .limit(limit + 1)).all()
    selected, next_cursor = page([r[0] for r in rows], limit, "created_at")
    names = {incident.id: name for incident, name in rows}
    return {"items": [incident_out(row, names[row.id]) for row in selected],
            "next_cursor": next_cursor}


@router.get("/incidents/{incident_id}")
def detail(incident_id: uuid.UUID, db: Annotated[Session, Depends(get_db)],
           user: Annotated[User, Depends(current_user)]):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, "NOT_FOUND", "Incident not found")
    require_service(db, user, incident.service_id)
    service = db.get(Service, incident.service_id)
    events = db.scalars(select(IncidentEvent).where(IncidentEvent.incident_id == incident.id)
                        .order_by(IncidentEvent.occurred_at.desc(), IncidentEvent.id.desc())
                        .limit(100)).all()
    alerts = db.scalars(select(AlertEvent).where(AlertEvent.incident_id == incident.id)
                        .order_by(AlertEvent.occurred_at)).all()
    return {**incident_out(incident, service.name),
            "timeline": [{"id": str(e.id), "occurred_at": e.occurred_at,
                          "type": e.event_type, "message": e.message} for e in reversed(events)],
            "alerts": [{"id": str(a.id), "sample_id": str(a.sample_id),
                        "occurred_at": a.occurred_at, "observed_percent": a.observed_percent}
                       for a in alerts]}


@router.get("/incidents/{incident_id}/events")
def events(incident_id: uuid.UUID, db: Annotated[Session, Depends(get_db)],
           user: Annotated[User, Depends(current_user)],
           q: str | None = Query(None, max_length=100), cursor: str | None = None,
           limit: int = Query(30, ge=1, le=100)):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, "NOT_FOUND", "Incident not found")
    require_service(db, user, incident.service_id)
    query = select(IncidentEvent).where(IncidentEvent.incident_id == incident.id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(IncidentEvent.message.ilike(f"%{escaped}%", escape="\\"))
    boundary = after_cursor(IncidentEvent.occurred_at, IncidentEvent.id, cursor)
    if boundary is not None:
        query = query.where(boundary)
    rows = db.scalars(query.order_by(IncidentEvent.occurred_at.desc(), IncidentEvent.id.desc())
                      .limit(limit + 1)).all()
    selected, next_cursor = page(rows, limit, "occurred_at")
    return {"items": [{"id": str(e.id), "occurred_at": e.occurred_at,
                       "type": e.event_type, "message": e.message} for e in selected],
            "next_cursor": next_cursor}


class StatusChange(BaseModel):
    status: Literal["investigating", "resolved"]


@router.patch("/incidents/{incident_id}/status")
def change_status(incident_id: uuid.UUID, change: StatusChange,
                  db: Annotated[Session, Depends(get_db)], request: Request,
                  user: Annotated[User, Depends(require_roles("responder", "approver", "admin"))]):
    incident = db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
    if incident is None:
        raise ApiError(404, "NOT_FOUND", "Incident not found")
    require_service(db, user, incident.service_id)
    transition(db, incident, change.status, user.id)
    record(db, actor_id=user.id, action="incident.status", target_type="incident",
           target_id=str(incident.id), outcome="allowed", request_id=request.state.request_id,
           context={"status": change.status})
    db.commit()
    return {"id": str(incident.id), "status": incident.status}
