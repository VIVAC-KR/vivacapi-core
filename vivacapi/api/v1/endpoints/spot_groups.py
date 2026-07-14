from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.database import get_db
from vivacapi.core.deps import get_current_user, get_current_user_optional
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.region import abbreviate_sido
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_group as crud_group
from vivacapi.crud import spot_image as crud_image
from vivacapi.crud import user as crud_user
from vivacapi.models.spot_group import (
    GroupRole,
    GroupVisibility,
    SpotGroup,
    SpotGroupMember,
)
from vivacapi.models.user import User
from vivacapi.schemas.spot_group import (
    SpotGroupCreate,
    SpotGroupDetail,
    SpotGroupListItem,
    SpotGroupMemberInvite,
    SpotGroupMemberOut,
    SpotGroupMemberRoleUpdate,
    SpotGroupSpotAdd,
    SpotGroupSpotItem,
    SpotGroupUpdate,
)

router = APIRouter()

# 등급 간 순서 비교용 (core/deps.py의 _STAFF_ROLE_RANK와 동일한 이유).
_GROUP_ROLE_RANK = {
    GroupRole.VIEWER: 1,
    GroupRole.CONTRIBUTOR: 2,
    GroupRole.EDITOR: 3,
    GroupRole.OWNER: 4,
}


async def _get_group_or_404(
    group_uid: str, session: AsyncSession = Depends(get_db)
) -> SpotGroup:
    group = await crud_group.get_group_by_uid(session, group_uid)
    if group is None:
        raise AppException(ErrorCode.SPOT_GROUP_NOT_FOUND, "Group not found")
    return group


async def _get_readable_group(
    group: SpotGroup = Depends(_get_group_or_404),
    user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_db),
) -> SpotGroup:
    """PUBLIC이면 누구나, 아니면 멤버만 통과. 존재를 숨기려고 403이 아닌 404를 쓴다."""
    if group.visibility != GroupVisibility.PUBLIC:
        membership = (
            await crud_group.get_membership(session, group.uid, user.uid)
            if user
            else None
        )
        if membership is None:
            raise AppException(ErrorCode.SPOT_GROUP_NOT_FOUND, "Group not found")
    return group


async def _get_membership_or_404(
    group: SpotGroup = Depends(_get_group_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> tuple[SpotGroup, SpotGroupMember]:
    membership = await crud_group.get_membership(session, group.uid, user.uid)
    if membership is None:
        raise AppException(ErrorCode.SPOT_GROUP_NOT_FOUND, "Group not found")
    return group, membership


def require_group_role(min_role: GroupRole):
    """min_role 이상의 그룹 내 role만 통과시킨다. 멤버가 아니면 404(존재 은닉)."""

    async def _dependency(
        group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
            _get_membership_or_404
        ),
    ) -> tuple[SpotGroup, SpotGroupMember]:
        _, membership = group_and_membership
        if _GROUP_ROLE_RANK[GroupRole(membership.role)] < _GROUP_ROLE_RANK[min_role]:
            raise AppException(
                ErrorCode.FORBIDDEN, f"{min_role.value} 이상 권한이 필요합니다"
            )
        return group_and_membership

    return _dependency


async def _to_detail(
    session: AsyncSession, group: SpotGroup, my_role: GroupRole | None
) -> SpotGroupDetail:
    spot_count = await crud_group.count_group_spots(session, group.uid)
    return SpotGroupDetail(
        uid=group.uid,
        name=group.name,
        description=group.description,
        visibility=group.visibility,
        spot_count=spot_count,
        my_role=my_role,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.post("", response_model=SpotGroupDetail, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: SpotGroupCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupDetail:
    group = await crud_group.create_group(
        session,
        owner_uid=user.uid,
        name=payload.name,
        description=payload.description,
        visibility=payload.visibility,
    )
    return await _to_detail(session, group, GroupRole.OWNER)


@router.get("", response_model=list[SpotGroupListItem])
async def list_my_groups(
    user: User = Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[SpotGroupListItem]:
    rows = await crud_group.list_groups_for_user(
        session, user.uid, offset=offset, limit=limit
    )
    return [
        SpotGroupListItem(
            uid=group.uid,
            name=group.name,
            visibility=group.visibility,
            my_role=role,
            spot_count=spot_count,
            updated_at=group.updated_at,
        )
        for group, role, spot_count in rows
    ]


@router.get("/{group_uid}", response_model=SpotGroupDetail)
async def get_group(
    group: SpotGroup = Depends(_get_readable_group),
    user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupDetail:
    membership = (
        await crud_group.get_membership(session, group.uid, user.uid) if user else None
    )
    return await _to_detail(
        session, group, GroupRole(membership.role) if membership else None
    )


@router.patch("/{group_uid}", response_model=SpotGroupDetail)
async def update_group(
    payload: SpotGroupUpdate,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.EDITOR)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupDetail:
    group, membership = group_and_membership
    group = await crud_group.update_group(
        session, group, payload.model_dump(exclude_unset=True)
    )
    return await _to_detail(session, group, GroupRole(membership.role))


@router.delete("/{group_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> None:
    group, _ = group_and_membership
    await crud_group.delete_group(session, group)


@router.get("/{group_uid}/spots", response_model=list[SpotGroupSpotItem])
async def list_group_spots(
    group: SpotGroup = Depends(_get_readable_group),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[SpotGroupSpotItem]:
    rows = await crud_group.list_group_spots(
        session, group.uid, offset=offset, limit=limit
    )
    thumbnails = await crud_image.get_thumbnails_by_spots(
        session, [spot.uid for spot, _ in rows]
    )
    return [
        SpotGroupSpotItem(
            uid=spot.uid,
            title=spot.title,
            trust_tier=spot.trust_tier,
            category=spot.category,
            region_short=abbreviate_sido(spot.region_province),
            thumbnail_url=(
                storage.resolve_url(image.s3_key, image.is_public)
                if (image := thumbnails.get(spot.uid))
                else None
            ),
            added_by_uid=item.added_by_uid,
            added_at=item.created_at,
        )
        for spot, item in rows
    ]


@router.post(
    "/{group_uid}/spots",
    response_model=SpotGroupSpotItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_spot(
    payload: SpotGroupSpotAdd,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.CONTRIBUTOR)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupSpotItem:
    group, membership = group_and_membership
    spot = await crud_spot.get_spot_by_uid(
        session, payload.spot_uid, published_only=True
    )
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")

    item = await crud_group.add_spot(
        session,
        group_uid=group.uid,
        spot_uid=spot.uid,
        added_by_uid=membership.user_uid,
    )
    thumbnails = await crud_image.get_thumbnails_by_spots(session, [spot.uid])
    image = thumbnails.get(spot.uid)
    return SpotGroupSpotItem(
        uid=spot.uid,
        title=spot.title,
        trust_tier=spot.trust_tier,
        category=spot.category,
        region_short=abbreviate_sido(spot.region_province),
        thumbnail_url=storage.resolve_url(image.s3_key, image.is_public)
        if image
        else None,
        added_by_uid=item.added_by_uid,
        added_at=item.created_at,
    )


@router.delete("/{group_uid}/spots/{spot_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_spot(
    spot_uid: str,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.EDITOR)
    ),
    session: AsyncSession = Depends(get_db),
) -> None:
    group, _ = group_and_membership
    removed = await crud_group.remove_spot(session, group.uid, spot_uid)
    if not removed:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not in this group")


@router.get("/{group_uid}/members", response_model=list[SpotGroupMemberOut])
async def list_group_members(
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.VIEWER)
    ),
    session: AsyncSession = Depends(get_db),
) -> list[SpotGroupMember]:
    group, _ = group_and_membership
    return await crud_group.list_members(session, group.uid)


@router.post(
    "/{group_uid}/members",
    response_model=SpotGroupMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_group_member(
    payload: SpotGroupMemberInvite,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupMember:
    group, membership = group_and_membership
    if group.visibility == GroupVisibility.PRIVATE:
        raise AppException(
            ErrorCode.SPOT_GROUP_INVITE_NOT_ALLOWED,
            "PRIVATE 그룹은 멤버를 초대할 수 없습니다. visibility를 먼저 변경하세요.",
        )
    target = await crud_user.get_user_by_id(session, payload.user_uid)
    if target is None:
        raise AppException(ErrorCode.USER_NOT_FOUND, "User not found")

    return await crud_group.add_member(
        session,
        group_uid=group.uid,
        user_uid=target.uid,
        role=payload.role,
        invited_by_uid=membership.user_uid,
    )


@router.patch("/{group_uid}/members/{user_uid}", response_model=SpotGroupMemberOut)
async def update_group_member_role(
    user_uid: str,
    payload: SpotGroupMemberRoleUpdate,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupMember:
    group, _ = group_and_membership
    target = await crud_group.get_membership(session, group.uid, user_uid)
    if target is None:
        raise AppException(ErrorCode.SPOT_GROUP_MEMBER_NOT_FOUND, "Member not found")
    return await crud_group.update_member_role(session, target, payload.role)


@router.delete(
    "/{group_uid}/members/{user_uid}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_group_member(
    user_uid: str,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> None:
    group, _ = group_and_membership
    target = await crud_group.get_membership(session, group.uid, user_uid)
    if target is None:
        raise AppException(ErrorCode.SPOT_GROUP_MEMBER_NOT_FOUND, "Member not found")
    await crud_group.remove_member(session, target)
