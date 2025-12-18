import os
import re
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

Base = declarative_base()

class NeonDatabase:
    _engine = None
    _SessionLocal = None

    @classmethod
    def init(cls):
        """Initialize the engine and session factory if not already set."""
        if cls._engine is None:
            database_url = os.getenv("DATABASE_URL")
            async_url = re.sub(r"^postgresql:", "postgresql+asyncpg:", database_url)
            cls._engine = create_async_engine(async_url, echo=True, future=True)
            cls._SessionLocal = sessionmaker(
                bind=cls._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return cls._engine

    @classmethod
    def get_session_factory(cls):
        """Return the session factory."""
        if cls._SessionLocal is None:
            cls.init()
        return cls._SessionLocal

    @classmethod
    def get_session(cls) -> AsyncSession:
        """Return a new session instance """
        return cls.get_session_factory()()

    @classmethod
    async def dispose(cls):
        """Dispose engine + reset session factory."""
        if cls._engine:
            await cls._engine.dispose()
            cls._engine = None
            cls._SessionLocal = None
