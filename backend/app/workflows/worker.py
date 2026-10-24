"""Run separately: python -m app.workflows.worker"""
import logging
import signal
import time
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import text
from prometheus_client import start_http_server

from app.observability.telemetry import (WORKFLOW_DUE, WORKFLOW_OLDEST, WORKFLOW_STEPS,
    WORKFLOW_DURATION, configure_tracing, log_event, span, timer)

from app.core.db import get_engine
from app.workflows.service import claim, execute_claim, retry_after_error

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger('workflow-worker')
stopping = False


def stop(_signal, _frame):
    global stopping
    stopping = True


def update_queue_metrics(db: Session):
    row = db.execute(text("""SELECT count(*), coalesce(extract(epoch from now() - min(next_attempt_at)), 0)
        FROM workflows WHERE state = 'queued' AND next_attempt_at <= now()""")).one()
    WORKFLOW_DUE.set(row[0])
    WORKFLOW_OLDEST.set(max(0, row[1]))


def run_once() -> bool:
    engine = get_engine()
    with Session(engine) as db:
        claimed = claim(db)
        update_queue_metrics(db)
    if claimed is None:
        return False
    workflow_id, token = claimed
    WORKFLOW_STEPS.labels('claimed').inc()
    try:
        with span('workflow.step') as current_span, timer(WORKFLOW_DURATION):
            current_span.set_attribute('workflow.id', str(workflow_id))
            with Session(engine) as db:
                execute_claim(db, workflow_id, token)
        WORKFLOW_STEPS.labels('processed').inc()
    except Exception:
        # No exception text: it may contain a SQL value or private document text.
        WORKFLOW_STEPS.labels('error').inc()
        log_event(log, 'workflow_step_error', workflow_id=str(workflow_id))
        try:
            with Session(engine) as db:
                retry_after_error(db, workflow_id, token)
        except Exception:
            log_event(log, 'workflow_retry_error', workflow_id=str(workflow_id))
    return True


def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    configure_tracing('ops-worker')
    start_http_server(9101, addr='0.0.0.0')
    log_event(log, 'worker_started', worker_id=str(uuid.uuid4()))
    while not stopping:
        try:
            if not run_once():
                time.sleep(2)
        except Exception:
            log_event(log, 'queue_unavailable')
            time.sleep(5)
    log_event(log, 'worker_stopped')


if __name__ == '__main__':
    main()
