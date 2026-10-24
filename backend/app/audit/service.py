import uuid

from sqlalchemy.orm import Session

from app.audit.models import AuditEvent


def record(session: Session, *, actor_id: uuid.UUID | None, action: str,
           target_type: str, target_id: str | None, outcome: str,
           request_id: str, context: dict | None = None) -> None:
    # Only allowlist fields into context; never store credentials or bearer tokens.
    session.add(AuditEvent(actor_id=actor_id, action=action, target_type=target_type,
                           target_id=target_id, outcome=outcome, request_id=request_id,
                           context=context or {}))
