import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spot import Spot


async def list_spots(
    session: AsyncSession,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Spot], int, int]:
    total: int = await session.scalar(select(func.count()).select_from(Spot)) or 0
    total_pages = math.ceil(total / limit) if total > 0 else 0
    offset = (page - 1) * limit
    result = await session.execute(
        select(Spot).order_by(Spot.title).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total, total_pages


async def get_spot_by_uid(session: AsyncSession, uid: str) -> Spot | None:
    result = await session.execute(select(Spot).where(Spot.uid == uid))
    return result.scalar_one_or_none()
