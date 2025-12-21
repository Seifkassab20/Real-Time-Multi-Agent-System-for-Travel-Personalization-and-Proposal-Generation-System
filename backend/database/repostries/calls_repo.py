import uuid
from sqlalchemy import String, DateTime, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from backend.database.models.Base import Base
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.models.calls import Calls


class calls_repository:
 
    async def create(self, db: AsyncSession, call: Calls) -> Calls:
        db.add(call)
        await db.commit()
        await db.refresh(call)
        return call