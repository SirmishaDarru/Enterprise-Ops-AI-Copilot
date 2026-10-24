"""Durable approved diagnostic workflow.

Revision ID: 0005_workflows
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0005_workflows'
down_revision = '0004_investigations'
branch_labels = None
depends_on = None
U = UUID(as_uuid=True)
T = sa.DateTime(timezone=True)


def upgrade():
    op.create_table('workflows',
        sa.Column('id', U, primary_key=True),
        sa.Column('incident_id', U, sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('service_id', U, sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requester_id', U, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('idempotency_key', U, nullable=False),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('state', sa.String(25), nullable=False),
        sa.Column('phase', sa.String(25), nullable=False),
        sa.Column('diagnostics', JSONB),
        sa.Column('result', JSONB),
        sa.Column('attempts', sa.Integer, nullable=False),
        sa.Column('next_attempt_at', T, server_default=sa.func.now(), nullable=False),
        sa.Column('lease_until', T),
        sa.Column('lease_token', U),
        sa.Column('cancel_requested', sa.Boolean, nullable=False),
        sa.Column('error_code', sa.String(40)),
        sa.Column('created_at', T, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', T, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('requester_id', 'idempotency_key'),
        sa.CheckConstraint("state IN ('queued','running','awaiting_approval','completed','failed','cancelled')", name='ck_workflow_state'),
        sa.CheckConstraint("phase IN ('diagnostics','simulation','done')", name='ck_workflow_phase'))
    op.create_index('ix_workflow_queue', 'workflows', ['state', 'next_attempt_at', 'lease_until'])
    op.create_index('ix_workflow_requester', 'workflows', ['requester_id', 'created_at'])
    op.create_table('workflow_approvals',
        sa.Column('id', U, primary_key=True),
        sa.Column('workflow_id', U, sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan', JSONB, nullable=False),
        sa.Column('plan_hash', sa.String(64), nullable=False),
        sa.Column('decision', sa.String(10), nullable=False),
        sa.Column('approver_id', U, sa.ForeignKey('users.id')),
        sa.Column('decided_at', T),
        sa.Column('created_at', T, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('workflow_id'))
    op.create_table('workflow_effects',
        sa.Column('id', U, primary_key=True),
        sa.Column('workflow_id', U, sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action_key', sa.String(40), nullable=False),
        sa.Column('plan_hash', sa.String(64), nullable=False),
        sa.Column('outcome', JSONB, nullable=False),
        sa.Column('created_at', T, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('workflow_id', 'action_key'))
    op.create_table('workflow_events',
        sa.Column('id', U, primary_key=True),
        sa.Column('workflow_id', U, sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(40), nullable=False),
        sa.Column('detail', sa.String(300), nullable=False),
        sa.Column('actor_id', U, sa.ForeignKey('users.id')),
        sa.Column('created_at', T, server_default=sa.func.now(), nullable=False))
    op.create_index('ix_workflow_event_order', 'workflow_events', ['workflow_id', 'created_at', 'id'])


def downgrade():
    op.drop_table('workflow_events')
    op.drop_table('workflow_effects')
    op.drop_table('workflow_approvals')
    op.drop_table('workflows')
