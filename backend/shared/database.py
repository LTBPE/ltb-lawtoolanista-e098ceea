"""
SQLAlchemy async engine and session management.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import config

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_async_url() -> str:
    """
    Convert a pyodbc-style connection string to an async SQLAlchemy URL.

    The AZURE_SQL_CONNECTION_STRING is expected in ODBC Driver format:
        Driver={ODBC Driver 18 for SQL Server};Server=...;Database=...;Uid=...;Pwd=...
    or as a standard SQLAlchemy URL:
        mssql+pyodbc://...
    """
    cs = config.AZURE_SQL_CONNECTION_STRING
    if cs.startswith("mssql"):
        # Already in SQLAlchemy format; ensure async driver
        if "aioodbc" not in cs:
            cs = cs.replace("mssql+pyodbc", "mssql+aioodbc")
        return cs

    # ODBC format - URL-encode the DSN and wrap it
    import urllib.parse
    params = urllib.parse.quote_plus(cs)
    return f"mssql+aioodbc:///?odbc_connect={params}"


def get_engine() -> AsyncEngine:
    """Return a module-level cached async engine."""
    global _engine
    if _engine is None:
        url = _build_async_url()
        _engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )
        logger.info("SQLAlchemy async engine initialised")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return a module-level cached session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields an AsyncSession.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(...)
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine (call on app shutdown)."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("SQLAlchemy engine disposed")
