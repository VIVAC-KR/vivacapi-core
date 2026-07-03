from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.spot import Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo

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

# 정확일치 필터 + distinct(패싯) 조회가 허용된 컬럼 화이트리스트.
# 여기에 항목만 추가하면 필터/드롭다운에 새 필드가 붙는다.
_FILTERABLE = {
    "region_province": Spot.region_province,
    "source": Spot.source,
}
FILTERABLE_FIELDS = frozenset(_FILTERABLE)


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
    filters: dict[str, str | None] | None = None,
) -> tuple[list[Spot], int]:
    """오프셋 기반 어드민 목록. (items, total)을 반환한다.

    filters: 화이트리스트(_FILTERABLE) 컬럼에 대한 정확일치 필터를 AND로 조합.
    """
    query = select(Spot)
    if title:
        query = query.where(Spot.title.ilike(f"%{title}%"))
    for field, value in (filters or {}).items():
        col = _FILTERABLE.get(field)
        if col is not None and value:
            query = query.where(col == value)

    total = await session.scalar(
        select(func.count()).select_from(query.subquery())
    )

    column = _ADMIN_SORTABLE.get(sort, Spot.uid)
    ordering = column.desc() if order == "desc" else column.asc()
    result = await session.execute(
        query.order_by(ordering).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def list_distinct(session: AsyncSession, field: str) -> list[str]:
    """화이트리스트 컬럼의 distinct non-null 값 목록 (드롭다운 옵션용)."""
    col = _FILTERABLE[field]
    result = await session.execute(
        select(col).where(col.is_not(None)).distinct().order_by(col)
    )
    return list(result.scalars().all())


async def get_spot_stats(session: AsyncSession) -> dict:
    """대시보드용 집계 통계."""
    total = await session.scalar(select(func.count()).select_from(Spot)) or 0
    business_info_total = (
        await session.scalar(select(func.count()).select_from(SpotBusinessInfo))
    ) or 0
    missing_coordinates = (
        await session.scalar(
            select(func.count())
            .select_from(Spot)
            .where(or_(Spot.latitude.is_(None), Spot.longitude.is_(None)))
        )
    ) or 0

    async def grouped(column) -> list[dict]:
        key = func.coalesce(column, "(미지정)")
        result = await session.execute(
            select(key, func.count()).group_by(key).order_by(func.count().desc())
        )
        return [{"key": k, "count": c} for k, c in result.all()]

    return {
        "total": total,
        "business_info_total": business_info_total,
        "missing_coordinates": missing_coordinates,
        "by_source": await grouped(Spot.source),
        "by_region_province": await grouped(Spot.region_province),
    }


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
