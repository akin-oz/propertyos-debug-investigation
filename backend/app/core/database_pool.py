import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy import text
import logging
from ..config import settings
from ..models.identifiers import TenantId

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self) -> None:
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    async def initialize(self) -> None:
        """Initialize database connection pool"""
        try:
            raw_url = settings.database_url
            # Normalize scheme for asyncpg driver
            if raw_url.startswith("postgres://"):
                raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif raw_url.startswith("postgresql://"):
                raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

            self.engine = create_async_engine(
                raw_url,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=3600,  # Recycle connections every hour
                echo=False  # Set to True for SQL debugging
            )
            
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("✅ Database connection pool initialized")
            
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None
    
    async def close(self) -> None:
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
    
    @asynccontextmanager
    async def get_session(
        self, tenant_id: Optional[TenantId] = None
    ) -> AsyncIterator[AsyncSession]:
        """
        Yield an AsyncSession, optionally scoped to a tenant.

        When `tenant_id` is supplied the PostgreSQL session variable
        `app.current_tenant_id` is set via SET LOCAL before the caller's
        queries run.  This activates the RLS policies defined in migration
        001_rls_policies.sql — even if application code forgets a WHERE clause
        the DB will not return cross-tenant rows.

        SET LOCAL scopes the variable to the current transaction; it is
        automatically cleared when the session is returned to the pool.
        """
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        async with self.session_factory() as session:
            if tenant_id is not None:
                await session.execute(
                    text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                    {"tid": str(tenant_id)},
                )
            yield session


# Global database pool instance
db_pool: DatabasePool = DatabasePool()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: session without tenant scope (admin / migration use only)."""
    async with db_pool.get_session() as session:
        yield session
