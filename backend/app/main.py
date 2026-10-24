import logging
import time
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.routes import router as auth_router
from app.incidents.routes import router as incident_router
from app.evaluation.routes import router as evaluation_router
from app.investigation.routes import router as investigation_router
from app.knowledge.routes import router as knowledge_router
from app.workflows.routes import router as workflow_router
from app.telemetry.routes import router as telemetry_router
from app.telemetry.live_routes import router as live_demo_router
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import (ApiError, api_error_handler, http_error_handler,
                             validation_error_handler)

from app.observability.telemetry import HTTP_DURATION, HTTP_REQUESTS, configure_tracing, log_event, span, trace_id

settings = get_settings()
configure_tracing('ops-api')
log = logging.getLogger('ops-api')
app = FastAPI(title="Enterprise AI Operations Copilot", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.cors_origin],
                   allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(live_demo_router, prefix="/api/v1")
app.include_router(incident_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(investigation_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")


@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    started = time.monotonic()
    status = 500
    with span('http.request') as current_span:
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers['X-Request-ID'] = request.state.request_id
            if trace_id():
                response.headers['X-Trace-ID'] = trace_id()
            return response
        finally:
            route = request.scope.get('route')
            # Never label by raw URL, query string, user, or document ID.
            path = getattr(route, 'path', '/unmatched')
            method = request.method if request.method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE') else 'OTHER'
            elapsed = time.monotonic() - started
            if path != '/metrics':
                HTTP_REQUESTS.labels(method, path, str(status)).inc()
                HTTP_DURATION.labels(method, path).observe(elapsed)
                current_span.set_attribute('http.route', path)
                current_span.set_attribute('http.response.status_code', status)
                log_event(log, 'http_request', method=method, route=path, status=status,
                          duration_ms=round(elapsed * 1000, 1), request_id=request.state.request_id,
                          trace_id=trace_id())


@app.get('/metrics', include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/ready")
def ready(db: Annotated[Session, Depends(get_db)]):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise ApiError(503, "NOT_READY", "Database unavailable") from None
    return {"status": "ready"}
