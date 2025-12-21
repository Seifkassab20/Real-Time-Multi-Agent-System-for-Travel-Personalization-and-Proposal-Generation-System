import asyncio
from sqlalchemy import text
from dotenv import load_dotenv
from backend.database.db import NeonDatabase
from backend.database.models.Base import Base
from backend.database.models.customers import Customer
from backend.database.models.service_agents import ServiceAgent


load_dotenv()

Db = NeonDatabase()
engine = Db.init()

async def init_db():

    async with engine.begin() as conn:
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        print(f"✅ Created tables: {list(Base.metadata.tables.keys())}")

    print("✅ Database initialized successfully and sample data inserted.")

if __name__ == "__main__":
    asyncio.run(init_db())
