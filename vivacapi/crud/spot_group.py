from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.models.spot import Spot
from vivacapi.models.spot_group import (
    GroupRole,
    SpotGroup,
    SpotGroupMember,
    SpotGroupSpot,
)
from vivacapi.models.user import User

# 어드민 목록에서 정렬 가능한 컬럼 화이트리스트 (임의 속성 주입 방지)
_ADMIN_SORTABLE = {
    "uid": SpotGroup.uid,
    "name": SpotGroup.name,
    "visibility": SpotGroup.visibility,
    "created_at": SpotGroup.created_at,
    "updated_at": SpotGroup.updated_at,
}
SORTABLE_FIELDS = frozenset(_ADMIN_SORTABLE)


async def create_group(
    session: AsyncSession,
    *,
    owner_uid: str,
    name: str,
    description: str | None,
    visibility,
) -> SpotGroup:
    group = SpotGroup(name=name, description=description, visibility=visibility)
    session.add(group)
    await session.flush()

    session.add(
        SpotGroupMember(group_uid=group.uid, user_uid=owner_uid, role=GroupRole.OWNER)
    )
    await session.commit()
    await session.refresh(group)
    return group


async def get_group_by_uid(session: AsyncSession, uid: str) -> SpotGroup | None:
    result = await session.execute(select(SpotGroup).where(SpotGroup.uid == uid))
    return result.scalar_one_or_none()


async def get_membership(
    session: AsyncSession, group_uid: str, user_uid: str
) -> SpotGroupMember | None:
    result = await session.execute(
        select(SpotGroupMember).where(
            SpotGroupMember.group_uid == group_uid,
            SpotGroupMember.user_uid == user_uid,
        )
    )
    return result.scalar_one_or_none()


async def count_group_spots(session: AsyncSession, group_uid: str) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(SpotGroupSpot)
            .where(SpotGroupSpot.group_uid == group_uid)
        )
    ) or 0


async def list_groups_for_user(
    session: AsyncSession, user_uid: str, *, offset: int, limit: int
) -> list[tuple[SpotGroup, GroupRole, int]]:
    """user_uid가 멤버인 그룹 목록. (group, my_role, spot_count) 튜플로 반환."""
    spot_count_subq = (
        select(func.count(SpotGroupSpot.spot_uid))
        .where(SpotGroupSpot.group_uid == SpotGroup.uid)
        .correlate(SpotGroup)
        .scalar_subquery()
    )
    stmt = (
        select(SpotGroup, SpotGroupMember.role, spot_count_subq)
        .join(SpotGroupMember, SpotGroupMember.group_uid == SpotGroup.uid)
        .where(SpotGroupMember.user_uid == user_uid)
        .order_by(SpotGroup.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(group, role, count) for group, role, count in result.all()]


async def update_group(
    session: AsyncSession, group: SpotGroup, data: dict
) -> SpotGroup:
    for key, value in data.items():
        setattr(group, key, value)
    await session.commit()
    await session.refresh(group)
    return group


async def delete_group(session: AsyncSession, group: SpotGroup) -> None:
    await session.delete(group)
    await session.commit()


async def add_member(
    session: AsyncSession,
    *,
    group_uid: str,
    user_uid: str,
    role: GroupRole,
    invited_by_uid: str,
) -> SpotGroupMember:
    if await get_membership(session, group_uid, user_uid) is not None:
        raise AppException(
            ErrorCode.SPOT_GROUP_MEMBER_ALREADY_EXISTS, "Already a member of this group"
        )
    member = SpotGroupMember(
        group_uid=group_uid, user_uid=user_uid, role=role, invited_by_uid=invited_by_uid
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def list_members(session: AsyncSession, group_uid: str) -> list[SpotGroupMember]:
    result = await session.execute(
        select(SpotGroupMember)
        .where(SpotGroupMember.group_uid == group_uid)
        .order_by(SpotGroupMember.created_at)
    )
    return list(result.scalars().all())


async def _count_owners(session: AsyncSession, group_uid: str) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(SpotGroupMember)
            .where(
                SpotGroupMember.group_uid == group_uid,
                SpotGroupMember.role == GroupRole.OWNER,
            )
        )
    ) or 0


async def update_member_role(
    session: AsyncSession, member: SpotGroupMember, role: GroupRole
) -> SpotGroupMember:
    """last-owner 안전장치: 그룹의 유일한 owner를 강등할 수 없다."""
    if member.role == GroupRole.OWNER and role != GroupRole.OWNER:
        if await _count_owners(session, member.group_uid) <= 1:
            raise AppException(
                ErrorCode.SPOT_GROUP_LAST_OWNER_REQUIRED,
                "Group must keep at least one owner",
            )
    member.role = role
    await session.commit()
    await session.refresh(member)
    return member


async def remove_member(session: AsyncSession, member: SpotGroupMember) -> None:
    """last-owner 안전장치: 그룹의 유일한 owner를 제거할 수 없다."""
    if member.role == GroupRole.OWNER:
        if await _count_owners(session, member.group_uid) <= 1:
            raise AppException(
                ErrorCode.SPOT_GROUP_LAST_OWNER_REQUIRED,
                "Group must keep at least one owner",
            )
    await session.delete(member)
    await session.commit()


async def add_spot(
    session: AsyncSession, *, group_uid: str, spot_uid: str, added_by_uid: str
) -> SpotGroupSpot:
    existing = await session.execute(
        select(SpotGroupSpot).where(
            SpotGroupSpot.group_uid == group_uid, SpotGroupSpot.spot_uid == spot_uid
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AppException(
            ErrorCode.SPOT_GROUP_SPOT_ALREADY_EXISTS, "Spot already in this group"
        )
    item = SpotGroupSpot(
        group_uid=group_uid, spot_uid=spot_uid, added_by_uid=added_by_uid
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def remove_spot(session: AsyncSession, group_uid: str, spot_uid: str) -> bool:
    result = await session.execute(
        select(SpotGroupSpot).where(
            SpotGroupSpot.group_uid == group_uid, SpotGroupSpot.spot_uid == spot_uid
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return False
    await session.delete(item)
    await session.commit()
    return True


async def list_group_spots(
    session: AsyncSession, group_uid: str, *, offset: int, limit: int
) -> list[tuple[Spot, SpotGroupSpot]]:
    stmt = (
        select(Spot, SpotGroupSpot)
        .join(SpotGroupSpot, SpotGroupSpot.spot_uid == Spot.uid)
        .where(SpotGroupSpot.group_uid == group_uid)
        .order_by(SpotGroupSpot.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(spot, item) for spot, item in result.all()]


# ---------------------------------------------------------------------------
# 어드민 (vivac-console) — 멤버십 무관 조회/모더레이션
# ---------------------------------------------------------------------------


async def count_group_members(session: AsyncSession, group_uid: str) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(SpotGroupMember)
            .where(SpotGroupMember.group_uid == group_uid)
        )
    ) or 0


async def list_members_admin(
    session: AsyncSession, group_uid: str
) -> list[tuple[SpotGroupMember, User]]:
    """콘솔 화면 표시용 — user의 nickname/email을 함께 join한다."""
    stmt = (
        select(SpotGroupMember, User)
        .join(User, User.uid == SpotGroupMember.user_uid)
        .where(SpotGroupMember.group_uid == group_uid)
        .order_by(SpotGroupMember.created_at)
    )
    result = await session.execute(stmt)
    return [(member, user) for member, user in result.all()]


async def list_groups_admin(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
    sort: str = "uid",
    order: str = "asc",
    name_like: str | None = None,
    visibility: str | None = None,
    user_uid: str | None = None,
) -> tuple[list[tuple[SpotGroup, int, int]], int]:
    """오프셋 기반 어드민 목록. (group, member_count, spot_count) 리스트와 total을 반환."""
    query = select(SpotGroup)
    if name_like:
        query = query.where(SpotGroup.name.ilike(f"%{name_like}%"))
    if visibility:
        query = query.where(SpotGroup.visibility == visibility)
    if user_uid:
        query = query.join(
            SpotGroupMember, SpotGroupMember.group_uid == SpotGroup.uid
        ).where(SpotGroupMember.user_uid == user_uid)

    total = await session.scalar(select(func.count()).select_from(query.subquery()))

    column = _ADMIN_SORTABLE.get(sort, SpotGroup.uid)
    ordering = column.desc() if order == "desc" else column.asc()
    result = await session.execute(query.order_by(ordering).offset(offset).limit(limit))
    groups = list(result.scalars().all())

    member_counts = {
        group_uid: count
        for group_uid, count in (
            await session.execute(
                select(SpotGroupMember.group_uid, func.count())
                .where(SpotGroupMember.group_uid.in_([g.uid for g in groups]))
                .group_by(SpotGroupMember.group_uid)
            )
        ).all()
    }
    spot_counts = {
        group_uid: count
        for group_uid, count in (
            await session.execute(
                select(SpotGroupSpot.group_uid, func.count())
                .where(SpotGroupSpot.group_uid.in_([g.uid for g in groups]))
                .group_by(SpotGroupSpot.group_uid)
            )
        ).all()
    }
    items = [
        (group, member_counts.get(group.uid, 0), spot_counts.get(group.uid, 0))
        for group in groups
    ]
    return items, total or 0
