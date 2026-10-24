"""Idempotent, visibly synthetic operational fixture. No live telemetry ingestion."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.models import ServiceMembership, User
from app.incidents.models import AlertRule
from app.telemetry.models import (DeploymentEvent, LogEvent, MetricSample, Service,
                                  ServiceDependency)

BASE = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ops-copilot-stage2-fixture-v1")


def stable(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}")


def add_once(db: Session, model, values: dict) -> None:
    db.execute(insert(model).values(**values).on_conflict_do_nothing(index_elements=[model.id]))


def seed_demo(db: Session) -> dict:
    checkout = stable("service", "checkout-api")
    payments = stable("service", "payments-db")
    for identifier, name, description in (
        (checkout, "checkout-api", "Synthetic checkout request service"),
        (payments, "payments-db", "Synthetic downstream payment datastore"),
    ):
        add_once(db, Service, {"id": identifier, "name": name, "description": description})
    add_once(db, ServiceDependency, {"id": stable("dependency", "checkout-payments"),
                                    "service_id": checkout, "depends_on_id": payments})
    for user in db.scalars(select(User).where(User.email.in_([
        f"{role}@local.example" for role in ("viewer", "responder", "approver", "admin")
    ]))):
        for service_id in (checkout, payments):
            add_once(db, ServiceMembership,
                     {"id": stable("membership", f"{user.id}:{service_id}"),
                      "user_id": user.id, "service_id": service_id})

    rule_id = stable("rule", "checkout-error-rate")
    add_once(db, AlertRule, {"id": rule_id, "service_id": checkout,
                             "name": "Checkout error rate", "threshold_percent": 15,
                             "enabled": True})
    add_once(db, DeploymentEvent, {"id": stable("deployment", "checkout-v2"),
                                    "service_id": checkout, "occurred_at": BASE + timedelta(minutes=4),
                                    "version": "v2.0-demo", "description": "Synthetic deployment marker; causality unknown",
                                    "source": "synthetic"})

    for minute in range(12):
        failure = 5 <= minute <= 8
        for service_id, name in ((checkout, "checkout"), (payments, "payments")):
            count = 100 if name == "checkout" else 80
            errors = (31 + minute - 5) if failure and name == "checkout" else (2 if name == "checkout" else 1)
            latency = (930 + 25 * (minute - 5)) if failure and name == "checkout" else (110 if name == "checkout" else 48)
            add_once(db, MetricSample, {"id": stable("metric", f"{name}-{minute}"),
                                        "service_id": service_id,
                                        "observed_at": BASE + timedelta(minutes=minute),
                                        "request_count": count, "error_count": errors,
                                        "latency_p95_ms": latency, "source": "synthetic"})
            message = ("Database connection pool exhausted; checkout returned HTTP 500"
                       if failure and name == "checkout" else f"{name} request window normal")
            add_once(db, LogEvent, {"id": stable("log", f"{name}-{minute}"),
                                    "service_id": service_id,
                                    "occurred_at": BASE + timedelta(minutes=minute, seconds=30),
                                    "level": "ERROR" if failure and name == "checkout" else "INFO",
                                    "message": message, "source": "synthetic"})
    db.flush()
    return {"service_id": checkout, "rule_id": rule_id,
            "sample_ids": [stable("metric", f"checkout-{i}") for i in range(5, 9)]}
