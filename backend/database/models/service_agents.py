import uuid
from sqlalchemy import String, Column
from sqlalchemy.dialects.postgresql import UUID
from backend.database.models.Base import Base

class ServiceAgent(Base):
	__tablename__ = "service_agents"
	service_agent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	name = Column(String(100), nullable=False)
	department = Column(String(50), nullable=True)

