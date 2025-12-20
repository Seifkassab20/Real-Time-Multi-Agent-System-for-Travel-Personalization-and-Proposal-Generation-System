import uuid
from sqlalchemy import String, Column
from sqlalchemy.dialects.postgresql import UUID
from backend.database.models.Base import Base

class Customer(Base):
	__tablename__ = "customers"
	customer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	name = Column(String(100), nullable=False)
	phone = Column(String(15), nullable=True)
	
