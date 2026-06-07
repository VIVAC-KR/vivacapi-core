from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from vivacapi.core.config import settings

# ---------------------------------------------------------------------------
# Engine
# create_async_engine은 실제 연결을 즉시 맺지 않습니다 (lazy).
# SSH 터널이 먼저 열린 뒤 첫 쿼리 시점에 연결이 이루어지므로
# lifespan 순서(터널 시작 → 요청 처리)와 충돌하지 않습니다.
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.database_url,
    echo=settings.ENVIRONMENT == "local",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스 클래스."""


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 라우터에서 사용하는 DB 세션 의존성."""
    async with AsyncSessionLocal() as session:
        yield session
