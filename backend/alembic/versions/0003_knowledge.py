"""Permissioned knowledge corpus and hybrid search.

Revision ID: 0003_knowledge
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_knowledge"
down_revision = "0002_operational_data"
branch_labels = None
depends_on = None
U = UUID(as_uuid=True)


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("knowledge_documents",
        sa.Column("id", U, primary_key=True),
        sa.Column("service_id", U, sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("extracted_text", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_knowledge_documents_service", "knowledge_documents", ["service_id"])
    op.create_table("document_grants",
        sa.Column("id", U, primary_key=True),
        sa.Column("document_id", U, sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.UniqueConstraint("document_id", "role"))
    op.create_index("ix_document_grants_role", "document_grants", ["role", "document_id"])
    op.create_table("knowledge_chunks",
        sa.Column("id", U, primary_key=True),
        sa.Column("document_id", U, sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("page_number", sa.Integer),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("embedding", VECTOR(384), nullable=False),
        sa.UniqueConstraint("document_id", "ordinal"))
    op.create_index("ix_knowledge_chunk_document", "knowledge_chunks", ["document_id"])
    op.execute("CREATE INDEX ix_knowledge_chunk_fts ON knowledge_chunks USING gin (to_tsvector('english', content))")
    op.execute("CREATE INDEX ix_knowledge_chunk_vector ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)")
    op.create_table("knowledge_embedding_cache",
        sa.Column("id", U, primary_key=True),
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("embedding", VECTOR(384), nullable=False),
        sa.UniqueConstraint("model_id", "content_sha256"))


def downgrade():
    op.drop_table("knowledge_embedding_cache")
    op.drop_table("knowledge_chunks")
    op.drop_table("document_grants")
    op.drop_table("knowledge_documents")
