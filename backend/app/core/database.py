"""Async SQLAlchemy engine and session factory.

Provides the async engine, session maker, and declarative base
for all ORM models. Connection parameters come from Settings.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.app.core.config import get_settings

# Naming convention for constraints so Alembic can auto-generate
# deterministic migration names for indexes, FKs, etc.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Pool settings as named constants (rule §8.6: no magic numbers)
POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT_SECONDS = 30
POOL_RECYCLE_SECONDS = 1800


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _build_engine() -> AsyncEngine:
    """Create the async engine from settings."""
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        return create_async_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            echo=(settings.app_env == "development"),
        )
    return create_async_engine(
        settings.database_url,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        pool_recycle=POOL_RECYCLE_SECONDS,
        echo=(settings.app_env == "development"),
    )


engine = _build_engine()

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db_session)):
    """
    async with async_session_factory() as session:
        yield session
