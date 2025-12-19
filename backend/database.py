from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
import os
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

try:
    from models import Base
except ImportError:
    class Base(DeclarativeBase):
        pass

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(
    DATABASE_URL + "?prepared_statement_cache_size=0",
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
    },
    echo=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("База данных инициализирована!")


async def drop_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("Все таблицы удалены!")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


