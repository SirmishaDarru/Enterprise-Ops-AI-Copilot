import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.incidents.models import AlertEvent, AlertRule, Incident, IncidentEvent
from app.telemetry.models import MetricSample


def error_percent(sample: MetricSample) -> int:
    return (100 * sample.error_count) // sample.request_count if sample.request_count else 0


def evaluate(db: Session, rule: AlertRule, sample: MetricSample) -> uuid.UUID | None:
    # Serialize evaluations for one rule, including the duplicate-alert check.
    db.execute(select(AlertRule.id).where(AlertRule.id == rule.id).with_for_update()).scalar_one()
    if not rule.enabled or sample.service_id != rule.service_id or sample.request_count == 0:
        return None
    observed = error_percent(sample)
    if observed < rule.threshold_percent:
        return None
    existing = db.scalar(select(AlertEvent).where(AlertEvent.rule_id == rule.id,
                                                   AlertEvent.sample_id == sample.id))
    if existing:
        return existing.incident_id
    now = datetime.now(timezone.utc)
    incident_id = uuid.uuid4()
    inserted = db.execute(insert(Incident).values(
        id=incident_id, service_id=rule.service_id, rule_id=rule.id,
        title=f"{rule.name} above {rule.threshold_percent}%", status="open", severity="high",
        created_at=now, updated_at=now
    ).on_conflict_do_nothing(
        index_elements=[Incident.service_id, Incident.rule_id],
        index_where=text("status IN ('open', 'investigating')")
    ).returning(Incident.id)).scalar_one_or_none()
    if inserted is None:
        incident_id = db.scalar(select(Incident.id).where(
            Incident.service_id == rule.service_id, Incident.rule_id == rule.id,
            Incident.status.in_(("open", "investigating"))))
        if incident_id is None:
            raise ApiError(409, "INCIDENT_CONFLICT", "Incident changed during alert evaluation")
    else:
        db.add(IncidentEvent(id=uuid.uuid4(), incident_id=incident_id, occurred_at=now,
                             event_type="created", message="Threshold alert created incident from observed local HTTP traffic"
                             if sample.source == "live_demo" else "Synthetic threshold alert created incident"))
    result = db.execute(insert(AlertEvent).values(
        id=uuid.uuid4(), rule_id=rule.id, sample_id=sample.id, incident_id=incident_id,
        observed_percent=observed, occurred_at=sample.observed_at
    ).on_conflict_do_nothing(index_elements=[AlertEvent.rule_id, AlertEvent.sample_id])
                        .returning(AlertEvent.id)).scalar_one_or_none()
    if result:
        db.add(IncidentEvent(id=uuid.uuid4(), incident_id=incident_id, occurred_at=now,
                             event_type="alert", message=f"{'Observed local HTTP' if sample.source == 'live_demo' else 'Synthetic'} error rate {observed}% (threshold {rule.threshold_percent}%)"))
    return incident_id


TRANSITIONS = {"open": {"investigating", "resolved"},
               "investigating": {"resolved"}, "resolved": set()}


def transition(db: Session, incident: Incident, target: str, actor_id: uuid.UUID) -> None:
    if target not in TRANSITIONS.get(incident.status, set()):
        raise ApiError(409, "INVALID_TRANSITION", "Invalid incident state transition")
    old = incident.status
    incident.status = target
    incident.updated_at = datetime.now(timezone.utc)
    if target == "resolved":
        incident.resolved_at = incident.updated_at
    db.add(IncidentEvent(id=uuid.uuid4(), incident_id=incident.id,
                         occurred_at=incident.updated_at, event_type="status_changed",
                         message=f"Status changed from {old} to {target}", actor_id=actor_id))
