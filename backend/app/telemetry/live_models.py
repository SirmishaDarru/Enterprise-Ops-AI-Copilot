import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LiveDemoCursor(Base):
    __tablename__ = 'live_demo_cursors'
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey('services.id', ondelete='CASCADE'), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
