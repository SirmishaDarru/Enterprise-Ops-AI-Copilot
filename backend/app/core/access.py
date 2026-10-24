import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import ServiceMembership, User
from app.core.errors import ApiError
from app.telemetry.models import Service


def permitted_service_ids(db: Session, user: User):
    if user.role == "admin":
        return None  # unrestricted within the local single-organization model
    return select(ServiceMembership.service_id).where(ServiceMembership.user_id == user.id)


def require_service(db: Session, user: User, service_id: uuid.UUID) -> None:
    scope = permitted_service_ids(db, user)
    if scope is None and db.get(Service, service_id) is None:
        raise ApiError(404, "NOT_FOUND", "Service not found")
    if scope is not None and db.scalar(select(ServiceMembership.id).where(
        ServiceMembership.user_id == user.id, ServiceMembership.service_id == service_id
    )) is None:
        # Do not reveal whether an out-of-scope service exists.
        raise ApiError(404, "NOT_FOUND", "Service not found")
