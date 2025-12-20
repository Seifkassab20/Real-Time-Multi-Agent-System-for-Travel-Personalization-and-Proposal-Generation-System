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

        def insert_sample_data(sync_conn):
            # Insert 3 customers
            sync_conn.execute(
                Customer.__table__.insert(),
                [
                    {"name": "Alice Smith", "email": "alice@example.com", "phone": "1234567890"},
                    {"name": "Bob Johnson", "email": "bob@example.com", "phone": "2345678901"},
                    {"name": "Charlie Brown", "email": "charlie@example.com", "phone": "3456789012"},
                ]
            )
            # Insert 3 service agents
            sync_conn.execute(
                ServiceAgent.__table__.insert(),
                [
                    {"name": "Agent One", "department": "Support"},
                    {"name": "Agent Two", "department": "Support"},
                    {"name": "Agent Three", "department": "Support"},
                ]
            )

        await conn.run_sync(insert_sample_data)

    print("✅ Database initialized successfully and sample data inserted.")

if __name__ == "__main__":
    asyncio.run(init_db())
