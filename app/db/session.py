from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
_engine_kwargs: dict = {"echo": False, "future": True}
if _is_sqlite:
    # SQLite (тесты): NullPool, чтобы не переиспользовать соединение между
    # событийными циклами pytest-asyncio.
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, **_engine_kwargs)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI: сессия на запрос с commit/rollback."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
