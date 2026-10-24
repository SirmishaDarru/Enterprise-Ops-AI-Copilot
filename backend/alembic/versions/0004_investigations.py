"""Stored, audited investigation reports.

Revision ID: 0004_investigations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0004_investigations'
down_revision = '0003_knowledge'
branch_labels = None
depends_on = None
U = UUID(as_uuid=True)


def upgrade():
    op.create_table('investigations',
        sa.Column('id', U, primary_key=True),
        sa.Column('incident_id', U, sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_id', U, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('provider', sa.String(30), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('evidence', JSONB, nullable=False),
        sa.Column('report', JSONB),
        sa.Column('error_code', sa.String(40)),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('cost_usd', sa.String(30)),
        sa.Column('latency_ms', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_investigation_actor_incident', 'investigations',
                    ['actor_id', 'incident_id', 'created_at'])


def downgrade():
    op.drop_table('investigations')
