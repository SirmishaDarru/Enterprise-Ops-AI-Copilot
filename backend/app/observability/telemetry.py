import json
import logging
import os
import time
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter('ops_http_requests_total', 'API requests', ['method', 'route', 'status'])
HTTP_DURATION = Histogram('ops_http_request_duration_seconds', 'API latency', ['method', 'route'])
WORKFLOW_STEPS = Counter('ops_workflow_steps_total', 'Worker outcomes', ['result'])
WORKFLOW_DURATION = Histogram('ops_workflow_step_duration_seconds', 'Worker step latency')
WORKFLOW_DUE = Gauge('ops_workflow_due', 'Due workflow jobs visible to the worker')
WORKFLOW_OLDEST = Gauge('ops_workflow_oldest_due_seconds', 'Age of the oldest due job')


def configure_tracing(service_name: str):
    endpoint = os.getenv('OTEL_TRACES_ENDPOINT', '').strip()
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({'service.name': service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=3)))
    trace.set_tracer_provider(provider)


def span(name: str):
    return trace.get_tracer('ops-copilot').start_as_current_span(name)


def trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, '032x') if context.is_valid else None


def log_event(logger: logging.Logger, event: str, **fields):
    # Callers pass only fixed keys and public identifiers; never exception text or payloads.
    logger.info(json.dumps({'event': event, **fields}, separators=(',', ':')))


@contextmanager
def timer(histogram):
    started = time.monotonic()
    try:
        yield
    finally:
        histogram.observe(time.monotonic() - started)
