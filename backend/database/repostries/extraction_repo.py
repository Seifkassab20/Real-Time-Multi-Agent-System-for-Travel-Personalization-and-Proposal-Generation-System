from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select
from backend.database.models.extractions import Extraction
from uuid import UUID
from typing import Dict, Any


class ExtractionRepository:

    async def create(self, db: AsyncSession, extraction_data: Dict[str, Any]) -> Extraction:
        extraction = Extraction(**extraction_data)
        db.add(extraction)
        await db.commit()
        await db.refresh(extraction)
        return extraction

    async def update(self, db: AsyncSession, extraction_id: UUID, update_data: Dict[str, Any]) -> Extraction | None:

        if not update_data:
            return None

        stmt = (
            update(Extraction)
            .where(Extraction.extraction_id == extraction_id)
            .values(**update_data)
            .returning(Extraction)
        )
    

        result = await db.execute(stmt)
        await db.commit()

        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, extraction_id: UUID) -> Extraction | None:
        stmt = select(Extraction).where(Extraction.extraction_id == extraction_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


    async def get_by_call_id(self, db: AsyncSession, call_id: UUID) -> Extraction | None:
        stmt = select(Extraction).where(Extraction.call_id == call_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()