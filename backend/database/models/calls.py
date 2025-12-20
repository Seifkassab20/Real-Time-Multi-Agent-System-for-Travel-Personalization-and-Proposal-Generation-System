import uuid
from sqlalchemy import String, DateTime, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from backend.database.models.Base import Base


class Calls(Base):
    __tablename__ = "calls"
    call_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=True)
    service_agent_id = Column(UUID(as_uuid=True), ForeignKey("service_agents.service_agent_id"), nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    language = Column(String(10), nullable=True)
    status = Column(String(20), nullable=True)

