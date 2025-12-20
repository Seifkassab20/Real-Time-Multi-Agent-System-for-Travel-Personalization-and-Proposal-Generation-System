from uuid import UUID, uuid4
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, ConfigDict


class CustomerProfile(BaseModel):
    # IDs
    profile_id: UUID = Field(default_factory=uuid4)
    call_id: UUID

    # Dates
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # Budget
    budget_amount: Optional[Decimal] = None
    budget_currency: str = Field(default='EGP', max_length=6)

    # Travelers
    adults: Optional[int] = Field(default=None, ge=0)
    children: Optional[int] = Field(default=None, ge=0)
    ages: Optional[List[int]] = None 

    # Destination
    cities: Optional[List[str]] = None 
    specific_sites: Optional[List[str]] = None

    # Interests & Preferences
    interests: Optional[List[str]] = None 
    accommodation_preference: Optional[str] = Field(default=None, max_length=100)
    tour_style: Optional[str] = Field(default=None, max_length=200)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    # --- Optional: Custom Validators ---
    
    @field_validator('budget_currency')
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.upper()


class question_response(BaseModel):
    question: str
    fields_filling: List[str]

class profile_agent_response(BaseModel):
    questions: List[question_response]
