import uuid
from sqlalchemy import Column, String, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from backend.database.models.Base import Base


class Extraction(Base):
    __tablename__ = "extractions"

    extraction_id = Column( UUID(as_uuid=True),primary_key=True, default=uuid.uuid4)
    call_id = Column( UUID(as_uuid=True), ForeignKey("calls.call_id", ondelete="CASCADE"), nullable=False)
    budget = Column(String(50), nullable=True)
    adults = Column(String(10), nullable=True)
    children = Column(String(10), nullable=True)
    children_age = Column(String(50), nullable=True)
    rooms = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    check_in = Column(Date, nullable=True)
    check_out = Column(Date, nullable=True)
    activities = Column(ARRAY(String), nullable=True)
    preferences = Column(ARRAY(String), nullable=True)
    keywords = Column(ARRAY(String), nullable=True)
