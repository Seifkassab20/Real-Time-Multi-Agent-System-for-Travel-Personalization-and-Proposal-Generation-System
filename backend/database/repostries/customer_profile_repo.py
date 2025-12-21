from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database.models.customer_profile import CustomerProfileDB


class CustomerProfileRepository:
    """
    Repository for CustomerProfileDB.
    Encapsulates all database access logic (async).
    """
    
    async def create(self, db: AsyncSession, customer_profile: CustomerProfileDB) -> CustomerProfileDB:
        db.add(customer_profile)
        await db.commit()
        await db.refresh(customer_profile)
        return customer_profile
    
    async def update(self, db: AsyncSession, profile_id: UUID, update_data: dict) -> Optional[CustomerProfileDB]:
        """Update a customer profile by profile_id."""
        result = await db.execute(
            select(CustomerProfileDB).filter(CustomerProfileDB.profile_id == profile_id)
        )
        customer_profile = result.scalars().first()
        
        if customer_profile:
            for key, value in update_data.items():
                setattr(customer_profile, key, value)
            await db.commit()
            await db.refresh(customer_profile)
            return customer_profile
        return None

    async def get_by_call_id(self, db: AsyncSession, call_id: UUID) -> Optional[CustomerProfileDB]:
        """Retrieve a customer profile by call_id."""
        result = await db.execute(
            select(CustomerProfileDB).filter(CustomerProfileDB.call_id == call_id)
        )
        return result.scalars().first()

    async def get_by_profile_id(self, db: AsyncSession, profile_id: UUID) -> Optional[CustomerProfileDB]:
        """Retrieve a customer profile by profile_id."""
        result = await db.execute(
            select(CustomerProfileDB).filter(CustomerProfileDB.profile_id == profile_id)
        )
        return result.scalars().first()

    async def get_all(self, db: AsyncSession) -> List[CustomerProfileDB]:
        result = await db.execute(select(CustomerProfileDB))
        return result.scalars().all()
