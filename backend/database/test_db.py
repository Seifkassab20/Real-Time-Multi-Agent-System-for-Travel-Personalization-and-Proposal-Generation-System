import asyncio
from sqlalchemy import text
from dotenv import load_dotenv
from backend.database.db import NeonDatabase
from backend.database.models.Base import Base
load_dotenv()

# Initialize your custom Database wrapper
Db =NeonDatabase()
engine = Db.init()

async def init_db():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("Select *"))
        except Exception as e:
            print(f"⚠️ Skipping extension creation: {e}")
        
        # Create tables from your models
        await conn.run_sync(Base.metadata.create_all)

    print("✅ Database initialized")

if __name__ == "__main__":
    asyncio.run(init_db())
