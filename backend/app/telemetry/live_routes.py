"""Admin-only control of the internal local demo service."""
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.models import User
from app.auth.security import require_roles
from app.core.db import get_db
from app.core.errors import ApiError
from app.telemetry.live import SERVICE_ID, URL

router = APIRouter(prefix='/live-demo', tags=['live-demo'])
ADMIN = Annotated[User, Depends(require_roles('admin'))]
DB = Annotated[Session, Depends(get_db)]


class FailureMode(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool


def service_call(method: str, path: str, **kwargs) -> dict:
    try:
        with httpx.Client(base_url=URL, timeout=3, trust_env=False) as client:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise ApiError(503, 'LIVE_DEMO_UNAVAILABLE', 'Local checkout service unavailable') from None


@router.get('/status')
def status(_user: ADMIN):
    return {'service_id': str(SERVICE_ID), **service_call('GET', '/internal/state'),
            'origin': 'observed_local_http'}


@router.post('/failure')
def failure_mode(body: FailureMode, db: DB, request: Request, user: ADMIN):
    result = service_call('POST', '/internal/failure', json={'enabled': body.enabled})
    record(db, actor_id=user.id, action='live_demo.failure_mode', target_type='service',
           target_id=str(SERVICE_ID), outcome='allowed', request_id=request.state.request_id,
           context={'enabled': result['failure_enabled'], 'local_demo': True})
    db.commit()
    return {'service_id': str(SERVICE_ID), **result, 'origin': 'observed_local_http'}
