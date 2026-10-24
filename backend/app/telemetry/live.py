"""Pull actual checkout HTTP outcomes and commit aggregates, logs, alerts and cursor together."""
import logging
import math
import os
import signal
import time
import uuid
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.models import ServiceMembership, User
from app.core.db import get_engine
from app.incidents.models import AlertRule
from app.incidents.service import evaluate
from app.observability.telemetry import log_event, span
from app.telemetry.live_models import LiveDemoCursor
from app.telemetry.models import LogEvent, MetricSample, Service

SERVICE_ID = uuid.uuid5(uuid.NAMESPACE_DNS, 'ops-copilot:live-checkout-demo')
RULE_ID = uuid.uuid5(uuid.NAMESPACE_DNS, 'ops-copilot:live-checkout-error-rate')
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, 'ops-copilot:live-http-events')
URL = os.getenv('LIVE_DEMO_URL', 'http://checkout-demo:8081').rstrip('/')
log = logging.getLogger('live-collector')
stopping = False


def prepare(db: Session):
    db.execute(insert(Service).values(id=SERVICE_ID, name='live-checkout-demo',
        description='Local checkout service; metrics derived from handled HTTP requests')
        .on_conflict_do_nothing(index_elements=[Service.id]))
    db.execute(insert(AlertRule).values(id=RULE_ID, service_id=SERVICE_ID,
        name='Live checkout error rate', threshold_percent=20, enabled=True)
        .on_conflict_do_nothing(index_elements=[AlertRule.id]))
    for user in db.scalars(select(User).where(User.email.in_(
            [f'{role}@local.example' for role in ('viewer', 'responder', 'approver', 'admin')]))):
        db.execute(insert(ServiceMembership).values(user_id=user.id, service_id=SERVICE_ID)
            .on_conflict_do_nothing(index_elements=['user_id', 'service_id']))
    db.execute(insert(LiveDemoCursor).values(service_id=SERVICE_ID, instance_id='', last_seq=0)
        .on_conflict_do_nothing(index_elements=[LiveDemoCursor.service_id]))
    db.commit()


def checked_events(data: dict, after: int) -> list[dict]:
    events = data.get('events')
    if not isinstance(events, list) or len(events) > 200:
        raise ValueError('Invalid event batch')
    seen = after
    for event in events:
        if (type(event.get('seq')) is not int or event['seq'] <= seen
                or event.get('status') not in (200, 503)
                or type(event.get('latency_ms')) is not int
                or not 0 <= event['latency_ms'] <= 10000):
            raise ValueError('Invalid checkout event')
        timestamp = datetime.fromisoformat(event['at'])
        if timestamp.tzinfo is None:
            raise ValueError('Unzoned checkout event')
        seen = event['seq']
    return events


def ingest(db: Session, client: httpx.Client) -> dict:
    cursor = db.scalar(select(LiveDemoCursor).where(LiveDemoCursor.service_id == SERVICE_ID)
                       .with_for_update())
    if cursor is None:
        raise ValueError('Collector cursor not initialized')
    response = client.get('/internal/events', params={'after': cursor.last_seq}, timeout=3)
    response.raise_for_status()
    data = response.json()
    instance = str(uuid.UUID(data['instance_id']))
    if instance != cursor.instance_id:
        cursor.instance_id = instance
        cursor.last_seq = 0
        response = client.get('/internal/events', params={'after': 0}, timeout=3)
        response.raise_for_status()
        data = response.json()
        if str(uuid.UUID(data['instance_id'])) != instance:
            raise ValueError('Checkout service restarted during poll')
    events = checked_events(data, cursor.last_seq)
    if not events:
        db.commit()
        return {'ingested': 0, 'alert': False}
    if events[0]['seq'] > cursor.last_seq + 1:
        # Ring buffer overflow is visible as a gap, never silently called complete.
        db.add(LogEvent(id=uuid.uuid5(NAMESPACE, f'{instance}:gap:{events[0]["seq"]}'),
            service_id=SERVICE_ID, occurred_at=datetime.fromisoformat(events[0]['at']),
            level='WARN', message='Checkout event buffer gap; aggregate is incomplete',
            source='live_demo'))
    latencies = sorted(item['latency_ms'] for item in events)
    last = events[-1]
    sample = MetricSample(id=uuid.uuid5(NAMESPACE, f'{instance}:batch:{last["seq"]}'),
        service_id=SERVICE_ID, observed_at=datetime.fromisoformat(last['at']),
        request_count=len(events), error_count=sum(item['status'] == 503 for item in events),
        latency_p95_ms=latencies[math.ceil(0.95 * len(latencies)) - 1], source='live_demo')
    db.add(sample)
    for item in events:
        if item['status'] == 503:
            db.add(LogEvent(id=uuid.uuid5(NAMESPACE, f'{instance}:event:{item["seq"]}'),
                service_id=SERVICE_ID, occurred_at=datetime.fromisoformat(item['at']),
                level='ERROR', message='Database connection pool exhausted; checkout HTTP 503',
                source='live_demo'))
    db.flush()
    rule = db.get(AlertRule, RULE_ID)
    incident_id = evaluate(db, rule, sample)
    cursor.last_seq = last['seq']
    db.commit()
    return {'ingested': len(events), 'alert': incident_id is not None}


def stop(_signal, _frame):
    global stopping
    stopping = True


def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    engine = get_engine()
    with httpx.Client(base_url=URL, trust_env=False) as client:
        while not stopping:
            try:
                with Session(engine) as db:
                    prepare(db)
                    with span('live_checkout.ingest'):
                        result = ingest(db, client)
                    if result['ingested']:
                        log_event(log, 'checkout_batch', count=result['ingested'], alert=result['alert'])
            except Exception:
                # Do not log exception text: HTTP and database exceptions may contain private content.
                log_event(log, 'checkout_ingest_retry')
            time.sleep(3)


if __name__ == '__main__':
    main()
