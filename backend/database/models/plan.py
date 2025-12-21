import uuid
from sqlalchemy import String, DateTime,Column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.schema import ForeignKey
from backend.database.models.Base import Base
from sqlalchemy import func
class ItineraryDB(Base):
    __tablename__ = "itineraries"
    itinerary_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id = Column(UUID(as_uuid=True), nullable=False)
    itinerary_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    call_id = ForeignKey("calls.call_id", ondelete="CASCADE")