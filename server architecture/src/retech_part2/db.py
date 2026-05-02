from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from retech_part2.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


def reset_db_cache_for_new_loop() -> None:
    """Drop the cached engine + session factory.

    Required in long-lived processes that call ``asyncio.run()`` per task or
    event (RQ worker, watchdog handler). The async engine's connection pool
    is bound to whichever event loop created it; reusing it from a fresh
    loop raises ``RuntimeError: got Future attached to a different loop``.
    Call this immediately before each ``asyncio.run()`` call in those
    contexts. The previous engine is intentionally not disposed (its
    ``dispose()`` itself touches the dead loop) — the leftover connection
    pool is reclaimed at process exit.
    """
    get_engine.cache_clear()
    get_session_factory.cache_clear()
