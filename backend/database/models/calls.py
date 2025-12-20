import uuid
from sqlalchemy import String, DateTime, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from backend.database.models.Base import Base


class Calls(Base):
    __tablename__ = "calls"
    call_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_context=Column(JSONB, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
  
