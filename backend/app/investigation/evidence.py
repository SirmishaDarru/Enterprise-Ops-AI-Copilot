"""Collect bounded, scoped evidence. Document passages are untrusted data."""
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.access import require_service
from app.core.errors import ApiError
from app.incidents.models import AlertEvent, Incident
from app.knowledge.models import Document
from app.knowledge.routes import search as search_knowledge
from app.telemetry.models import (DeploymentEvent, LogEvent, MetricSample, Service,
                                  ServiceDependency)


def collect(db: Session, user: User, incident_id: uuid.UUID) -> tuple[Incident, list[dict], list[str]]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(404, 'NOT_FOUND', 'Incident not found')
    require_service(db, user, incident.service_id)
    service = db.get(Service, incident.service_id)
    evidence: list[dict] = []
    gaps: list[str] = []

    def add(kind: str, identifier: uuid.UUID, detail: str, occurred_at=None, source_url=None):
        evidence.append({'id': f'{kind}:{identifier}', 'kind': kind, 'detail': detail[:700],
                         'occurred_at': occurred_at.isoformat() if occurred_at else None,
                         'source_url': source_url})

    alerts = db.scalars(select(AlertEvent).where(AlertEvent.incident_id == incident.id)
                        .order_by(AlertEvent.occurred_at, AlertEvent.id).limit(20)).all()
    for alert in alerts:
        add('alert', alert.id, f'{alert.observed_percent}% error rate at alert threshold',
            alert.occurred_at)
        sample = db.get(MetricSample, alert.sample_id)
        if sample:
            add('metric', sample.id,
                f'{sample.error_count}/{sample.request_count} errors; p95 {sample.latency_p95_ms} ms; source {sample.source}',
                sample.observed_at)
    if not alerts:
        gaps.append('No alert samples are attached to this incident.')
    earliest = min((a.occurred_at for a in alerts), default=None)
    latest = max((a.occurred_at for a in alerts), default=None)
    if earliest and latest:
        window = (earliest - timedelta(minutes=3), latest + timedelta(minutes=3))
        logs = db.scalars(select(LogEvent).where(LogEvent.service_id == incident.service_id,
            LogEvent.occurred_at.between(*window)).order_by(LogEvent.occurred_at).limit(12)).all()
        deployments = db.scalars(select(DeploymentEvent).where(
            DeploymentEvent.service_id == incident.service_id,
            DeploymentEvent.occurred_at.between(*window)).order_by(
            DeploymentEvent.occurred_at).limit(5)).all()
        for log in logs:
            add('log', log.id, f'{log.level}: {log.message}', log.occurred_at)
        for deployment in deployments:
            add('deployment', deployment.id,
                f'{deployment.version}: {deployment.description}; timing alone does not prove cause',
                deployment.occurred_at)
        if not logs:
            gaps.append('No service logs were found near the alert window.')
    dependencies = db.scalars(select(ServiceDependency).where(
        ServiceDependency.service_id == incident.service_id).limit(10)).all()
    for dependency in dependencies:
        downstream = db.get(Service, dependency.depends_on_id)
        if downstream:
            add('dependency', dependency.id,
                f'{service.name} depends on {downstream.name}; dependency is not proof of failure')
    past = db.scalars(select(Incident).where(Incident.service_id == incident.service_id,
        Incident.id != incident.id).order_by(Incident.created_at.desc()).limit(5)).all()
    for previous in past:
        add('historical_incident', previous.id,
            f'{previous.title}; status {previous.status}; historical similarity is not proof',
            previous.created_at)
    if not past:
        gaps.append('No prior incidents for this service are available to compare.')

    if db.scalar(select(Document.id).where(Document.service_id == incident.service_id).limit(1)):
        try:
            hits = search_knowledge(db, user, f'{service.name} connection pool error runbook',
                                    incident.service_id)['items'][:5]
        except ApiError as exc:
            if exc.code != 'EMBEDDING_UNAVAILABLE':
                raise
            hits = []
            gaps.append('Document retrieval was unavailable; check local embedding model.')
        for hit in hits:
            add('source', uuid.UUID(hit['source_id']),
                f"{hit['title']} (v{hit['version']}): {hit['snippet'][:500]}",
                source_url=f"/api/v1/knowledge/sources/{hit['source_id']}")
    if not any(item['kind'] == 'source' for item in evidence):
        gaps.append('No accessible runbook passage was retrieved for this service.')
    return incident, evidence[:60], gaps
