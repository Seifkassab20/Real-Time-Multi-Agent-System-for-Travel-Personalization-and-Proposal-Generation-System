from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.database.models.customer_profile import CustomerProfileDB


class CustomerProfileRepository:
    """
    Repository for CustomerProfileDB.
    Encapsulates all database access logic.
    """
    def create(self, db: Session, customer_profile: CustomerProfileDB):
        db.add(customer_profile)
        db.commit()
        db.refresh(customer_profile)
        return customer_profile
    #retrieve BY CALL ID
    def get_by_call_id(self, db: Session, call_id: UUID):
        return db.query(CustomerProfileDB).filter(CustomerProfileDB.call_id == call_id).first()

    def get_all(self, db: Session):
        return db.query(CustomerProfileDB).all()
