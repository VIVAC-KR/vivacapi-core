from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.spot import Spot

# 어드민 목록에서 정렬 가능한 컬럼 화이트리스트 (임의 속성 주입 방지)
_ADMIN_SORTABLE = {
    "uid": Spot.uid,
    "title": Spot.title,
    "region_province": Spot.region_province,
    "region_city": Spot.region_city,
    "rating_avg": Spot.rating_avg,
    "review_count": Spot.review_count,
    "created_at": Spot.created_at,
    "updated_at": Spot.updated_at,
}


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


async def list_spots_admin(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
    sort: str = "uid",
    order: str = "asc",
    title: str | None = None,
    region_province: str | None = None,
) -> tuple[list[Spot], int]:
    """오프셋 기반 어드민 목록. (items, total)을 반환한다."""
    query = select(Spot)
    if title:
        query = query.where(Spot.title.ilike(f"%{title}%"))
    if region_province:
        query = query.where(Spot.region_province == region_province)

    total = await session.scalar(
        select(func.count()).select_from(query.subquery())
    )

    column = _ADMIN_SORTABLE.get(sort, Spot.uid)
    ordering = column.desc() if order == "desc" else column.asc()
    result = await session.execute(
        query.order_by(ordering).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def list_spot_provinces(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(Spot.region_province)
        .where(Spot.region_province.is_not(None))
        .distinct()
        .order_by(Spot.region_province)
    )
    return list(result.scalars().all())


async def update_spot(
    session: AsyncSession, uid: str, data: dict
) -> Spot | None:
    spot = await get_spot_by_uid(session, uid)
    if spot is None:
        return None
    for key, value in data.items():
        setattr(spot, key, value)
    await session.commit()
    await session.refresh(spot)
    return spot
