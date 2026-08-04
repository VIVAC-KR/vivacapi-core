import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from vivacapi.core.config import settings

# echo=True를 쓰면 SQLAlchemy가 sqlalchemy.engine 로거에 자체 handler를 붙이는데,
# main.py의 basicConfig가 이미 root에 handler를 달아둬서 같은 줄이 두 번 찍힌다.
# 레벨만 올려 root handler 하나로 출력한다.
if settings.DB_ECHO:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Engine
# create_async_engine은 실제 연결을 즉시 맺지 않습니다 (lazy).
# SSH 터널이 먼저 열린 뒤 첫 쿼리 시점에 연결이 이루어지므로
# lifespan 순서(터널 시작 → 요청 처리)와 충돌하지 않습니다.
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.database_url,
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
