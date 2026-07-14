from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.spot import Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo

# 어드민 목록에서 정렬 가능한 컬럼 화이트리스트 (임의 속성 주입 방지)
_ADMIN_SORTABLE = {
    "uid": SpotBusinessInfo.uid,
    "spot_uid": SpotBusinessInfo.spot_uid,
    "business_type": SpotBusinessInfo.business_type,
    "operating_status": SpotBusinessInfo.operating_status,
    "created_at": SpotBusinessInfo.created_at,
    "updated_at": SpotBusinessInfo.updated_at,
}
SORTABLE_FIELDS = frozenset(_ADMIN_SORTABLE)


async def get_business_info_by_uid(
    session: AsyncSession, uid: str
) -> SpotBusinessInfo | None:
    result = await session.execute(
        select(SpotBusinessInfo).where(SpotBusinessInfo.uid == uid)
    )
    return result.scalar_one_or_none()


async def list_business_info_admin(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
    sort: str = "uid",
    order: str = "asc",
    spot_uid: str | None = None,
) -> tuple[list[SpotBusinessInfo], int]:
    """오프셋 기반 어드민 목록. (items, total)을 반환한다."""
    # 목록에 연관 spot 이름을 표시하려고 join한다 (spot_uid는 not null unique FK라
    # 카디널리티에 영향 없음).
    query = select(SpotBusinessInfo, Spot.title).join(
        Spot, Spot.uid == SpotBusinessInfo.spot_uid
    )
    if spot_uid:
        query = query.where(SpotBusinessInfo.spot_uid == spot_uid)

    total = await session.scalar(
        select(func.count()).select_from(query.subquery())
    )

    column = _ADMIN_SORTABLE.get(sort, SpotBusinessInfo.uid)
    ordering = column.desc() if order == "desc" else column.asc()
    result = await session.execute(
        query.order_by(ordering).offset(offset).limit(limit)
    )

    items = []
    for info, spot_title in result.all():
        info.spot_title = spot_title
        items.append(info)
    return items, total or 0


async def update_business_info(
    session: AsyncSession, uid: str, data: dict
) -> SpotBusinessInfo | None:
    info = await get_business_info_by_uid(session, uid)
    if info is None:
        return None
    for key, value in data.items():
        setattr(info, key, value)
    await session.commit()
    await session.refresh(info)
    return info
