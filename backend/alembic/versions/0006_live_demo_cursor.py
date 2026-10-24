"""Persist polling cursor with the aggregate and alert transaction."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006_live_demo_cursor'
down_revision = '0005_workflows'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('live_demo_cursors',
        sa.Column('service_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('services.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('instance_id', sa.String(36), nullable=False),
        sa.Column('last_seq', sa.Integer, nullable=False))


def downgrade():
    op.drop_table('live_demo_cursors')
