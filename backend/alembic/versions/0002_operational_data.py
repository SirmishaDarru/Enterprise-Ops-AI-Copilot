"""Synthetic operational data, alert rules, and incidents.

Revision ID: 0002_operational_data
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_operational_data"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

U = postgresql.UUID(as_uuid=True)
T = sa.DateTime(timezone=True)


def upgrade():
    op.create_table("metric_samples",
        sa.Column("id", U, primary_key=True),
        sa.Column("service_id", U, sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", T, nullable=False),
        sa.Column("request_count", sa.Integer, nullable=False),
        sa.Column("error_count", sa.Integer, nullable=False),
        sa.Column("latency_p95_ms", sa.Integer, nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.UniqueConstraint("service_id", "observed_at"),
        sa.CheckConstraint("request_count >= 0 AND error_count >= 0 AND error_count <= request_count AND latency_p95_ms >= 0", name="ck_metric_values"))
    op.create_index("ix_metric_service_time", "metric_samples", ["service_id", "observed_at"])
    op.create_table("log_events",
        sa.Column("id", U, primary_key=True),
        sa.Column("service_id", U, sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurred_at", T, nullable=False),
        sa.Column("level", sa.String(12), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("source", sa.String(30), nullable=False))
    op.create_index("ix_log_service_time", "log_events", ["service_id", "occurred_at"])
    op.create_table("deployment_events",
        sa.Column("id", U, primary_key=True),
        sa.Column("service_id", U, sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurred_at", T, nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("source", sa.String(30), nullable=False))
    op.create_table("alert_rules",
        sa.Column("id", U, primary_key=True),
        sa.Column("service_id", U, sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("threshold_percent", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.CheckConstraint("threshold_percent > 0 AND threshold_percent <= 100", name="ck_alert_threshold"))
    op.create_table("incidents",
        sa.Column("id", U, primary_key=True),
        sa.Column("service_id", U, sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", U, sa.ForeignKey("alert_rules.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("created_at", T, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", T, server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", T),
        sa.CheckConstraint("status IN ('open','investigating','resolved')", name="ck_incident_status"))
    op.create_index("ux_incident_active_rule", "incidents", ["service_id", "rule_id"],
                    unique=True, postgresql_where=sa.text("status IN ('open', 'investigating')"))
    op.create_index("ix_incident_created", "incidents", ["created_at", "id"])
    op.create_table("alert_events",
        sa.Column("id", U, primary_key=True),
        sa.Column("rule_id", U, sa.ForeignKey("alert_rules.id"), nullable=False),
        sa.Column("sample_id", U, sa.ForeignKey("metric_samples.id"), nullable=False),
        sa.Column("incident_id", U, sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("observed_percent", sa.Integer, nullable=False),
        sa.Column("occurred_at", T, nullable=False),
        sa.UniqueConstraint("rule_id", "sample_id"))
    op.create_table("incident_events",
        sa.Column("id", U, primary_key=True),
        sa.Column("incident_id", U, sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurred_at", T, nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("actor_id", U, sa.ForeignKey("users.id")))
    op.create_index("ix_incident_event_order", "incident_events", ["incident_id", "occurred_at", "id"])


def downgrade():
    op.drop_index("ix_incident_event_order", table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_table("alert_events")
    op.drop_index("ix_incident_created", table_name="incidents")
    op.drop_index("ux_incident_active_rule", table_name="incidents")
    op.drop_table("incidents")
    op.drop_table("alert_rules")
    op.drop_table("deployment_events")
    op.drop_index("ix_log_service_time", table_name="log_events")
    op.drop_table("log_events")
    op.drop_index("ix_metric_service_time", table_name="metric_samples")
    op.drop_table("metric_samples")
