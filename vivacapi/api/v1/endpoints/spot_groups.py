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


@router.post(
    "",
    response_model=SpotGroupDetail,
    status_code=status.HTTP_201_CREATED,
    summary="그룹 생성",
)
async def create_group(
    payload: SpotGroupCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupDetail:
    """요청한 사용자를 OWNER로 하는 새 그룹을 만든다. visibility를 생략하면 PRIVATE로 생성된다."""
    group = await crud_group.create_group(
        session,
        owner_uid=user.uid,
        name=payload.name,
        description=payload.description,
        visibility=payload.visibility,
    )
    return await _to_detail(session, group, GroupRole.OWNER)


@router.get("", response_model=list[SpotGroupListItem], summary="내 그룹 목록 조회")
async def list_my_groups(
    user: User = Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[SpotGroupListItem]:
    """로그인한 사용자가 멤버로 속한 그룹만 반환한다(공개 그룹이라도 비멤버면 나오지 않음). 각 항목에 본인의 my_role이 포함된다."""
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


@router.get("/{group_uid}", response_model=SpotGroupDetail, summary="그룹 상세 조회")
async def get_group(
    group: SpotGroup = Depends(_get_readable_group),
    user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupDetail:
    """PUBLIC 그룹은 비로그인 사용자도 조회할 수 있다. PRIVATE/INVITE_ONLY는 멤버만 조회 가능하며, 비멤버에게는 존재를 숨기기 위해 403 대신 404를 반환한다."""
    membership = (
        await crud_group.get_membership(session, group.uid, user.uid) if user else None
    )
    return await _to_detail(
        session, group, GroupRole(membership.role) if membership else None
    )


@router.patch("/{group_uid}", response_model=SpotGroupDetail, summary="그룹 정보 수정")
async def update_group(
    payload: SpotGroupUpdate,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.EDITOR)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupDetail:
    """name/description/visibility 중 전달된 필드만 수정한다. EDITOR 이상 권한이 필요하다."""
    group, membership = group_and_membership
    group = await crud_group.update_group(
        session, group, payload.model_dump(exclude_unset=True)
    )
    return await _to_detail(session, group, GroupRole(membership.role))


@router.delete(
    "/{group_uid}", status_code=status.HTTP_204_NO_CONTENT, summary="그룹 삭제"
)
async def delete_group(
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> None:
    """그룹과 소속 멤버·스팟 관계를 모두 삭제하는 비가역 작업이다. OWNER만 실행할 수 있다."""
    group, _ = group_and_membership
    await crud_group.delete_group(session, group)


@router.get(
    "/{group_uid}/spots",
    response_model=list[SpotGroupSpotItem],
    summary="그룹 스팟 목록 조회",
)
async def list_group_spots(
    group: SpotGroup = Depends(_get_readable_group),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[SpotGroupSpotItem]:
    """그룹에 담긴 스팟을 최근 추가 순으로 반환한다. get_group과 동일한 공개 범위 규칙이 적용된다."""
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
    summary="그룹에 스팟 추가",
)
async def add_group_spot(
    payload: SpotGroupSpotAdd,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.CONTRIBUTOR)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupSpotItem:
    """게시된(published) 스팟만 추가할 수 있다. CONTRIBUTOR 이상 권한이 필요하며, 이미 담긴 스팟이면 충돌 에러가 발생한다."""
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


@router.delete(
    "/{group_uid}/spots/{spot_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="그룹에서 스팟 제거",
)
async def remove_group_spot(
    spot_uid: str,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.EDITOR)
    ),
    session: AsyncSession = Depends(get_db),
) -> None:
    """EDITOR 이상 권한이 필요하다."""
    group, _ = group_and_membership
    removed = await crud_group.remove_spot(session, group.uid, spot_uid)
    if not removed:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not in this group")


@router.get(
    "/{group_uid}/members",
    response_model=list[SpotGroupMemberOut],
    summary="그룹 멤버 목록 조회",
)
async def list_group_members(
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.VIEWER)
    ),
    session: AsyncSession = Depends(get_db),
) -> list[SpotGroupMember]:
    """그룹 멤버만 조회할 수 있다(VIEWER 이상)."""
    group, _ = group_and_membership
    return await crud_group.list_members(session, group.uid)


@router.post(
    "/{group_uid}/members",
    response_model=SpotGroupMemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="멤버 초대",
)
async def invite_group_member(
    payload: SpotGroupMemberInvite,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupMember:
    """user_uid로 지정한 사용자를 곧바로 멤버로 등록한다(초대 코드·수락 절차·만료 없음). PRIVATE 그룹은 초대할 수 없고, OWNER만 실행할 수 있다."""
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


@router.patch(
    "/{group_uid}/members/{user_uid}",
    response_model=SpotGroupMemberOut,
    summary="멤버 역할 변경",
)
async def update_group_member_role(
    user_uid: str,
    payload: SpotGroupMemberRoleUpdate,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotGroupMember:
    """OWNER만 실행할 수 있다. 그룹에 남은 유일한 owner는 강등할 수 없다(다른 멤버를 먼저 owner로 지정해야 함)."""
    group, _ = group_and_membership
    target = await crud_group.get_membership(session, group.uid, user_uid)
    if target is None:
        raise AppException(ErrorCode.SPOT_GROUP_MEMBER_NOT_FOUND, "Member not found")
    return await crud_group.update_member_role(session, target, payload.role)


@router.delete(
    "/{group_uid}/members/{user_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="멤버 추방",
)
async def remove_group_member(
    user_uid: str,
    group_and_membership: tuple[SpotGroup, SpotGroupMember] = Depends(
        require_group_role(GroupRole.OWNER)
    ),
    session: AsyncSession = Depends(get_db),
) -> None:
    """OWNER만 실행할 수 있다. 그룹에 남은 유일한 owner는 제거할 수 없다."""
    group, _ = group_and_membership
    target = await crud_group.get_membership(session, group.uid, user_uid)
    if target is None:
        raise AppException(ErrorCode.SPOT_GROUP_MEMBER_NOT_FOUND, "Member not found")
    await crud_group.remove_member(session, target)
