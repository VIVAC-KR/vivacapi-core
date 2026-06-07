from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.spot import Spot


async def list_spots(
    session: AsyncSession,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[Spot], str | None, bool]:
    query = select(Spot).order_by(Spot.uid)
    if cursor:
        query = query.where(Spot.uid > cursor)
    result = await session.execute(query.limit(limit + 1))
    spots = list(result.scalars().all())

    has_more = len(spots) > limit
    if has_more:
        spots = spots[:limit]

    next_cursor = spots[-1].uid if has_more else None
    return spots, next_cursor, has_more


async def get_spot_by_uid(session: AsyncSession, uid: str) -> Spot | None:
    result = await session.execute(select(Spot).where(Spot.uid == uid))
    return result.scalar_one_or_none()
