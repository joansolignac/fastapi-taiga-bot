from functools import lru_cache

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from fastapi_taiga_bot.config import get_settings

@lru_cache
def get_engine():
    return create_async_engine(get_settings().database_url)

async def get_session() -> AsyncSession:
    session_factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session