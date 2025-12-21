from uuid import UUID, uuid4
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, ConfigDict


class question_response(BaseModel):
    question: str
    fields_filling: List[str]

class profile_agent_response(BaseModel):
    questions: List[question_response]
