import uuid
from datetime import date, datetime
from typing import List, Optional
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, Numeric, func, JSON, Column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from backend.database.models.Base import Base

# 2. Define the Table Model
class CustomerProfileDB(Base):
    __tablename__ = "customer_profiles"

    # IDs
    profile_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id = Column(UUID(as_uuid=True), nullable=False)

    # Dates
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # Budget
    budget_amount = Column(Integer, nullable=True)
    budget_currency = Column(String(3), nullable=True)

    # Travelers
    adults = Column(Integer, nullable=True)
    children = Column(Integer, nullable=True)
    

    ages = Column(JSONB, nullable=True)


    cities = Column(JSONB, nullable=True)
    specific_sites = Column(JSONB, nullable=True)

    # Interests & Preferences
    interests = Column(JSONB, nullable=True)
    accommodation_preference = Column(String(100), nullable=True)
    tour_style = Column(String(200), nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

