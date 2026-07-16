from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff, require_role
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.region import abbreviate_sido
from vivacapi.crud import spot_group as crud_group
from vivacapi.crud import spot_image as crud_image
from vivacapi.crud import user as crud_user
from vivacapi.models.spot_group import SpotGroup
from vivacapi.models.user import StaffRole
from vivacapi.schemas.spot_group import (
    SpotGroupAdminDetail,
    SpotGroupAdminListItem,
    SpotGroupAdminMemberOut,
    SpotGroupMemberInvite,
    SpotGroupMemberRoleUpdate,
    SpotGroupSpotItem,
    SpotGroupUpdate,
)

router = APIRouter()


async def _get_group_or_404(
    group_uid: str, db: AsyncSession = Depends(get_db)
) -> SpotGroup:
    group = await crud_group.get_group_by_uid(db, group_uid)
    if group is None:
        raise AppException(ErrorCode.SPOT_GROUP_NOT_FOUND, "Group not found")
    return group


async def _to_admin_detail(db: AsyncSession, group: SpotGroup) -> SpotGroupAdminDetail:
    return SpotGroupAdminDetail(
        uid=group.uid,
        name=group.name,
        description=group.description,
        visibility=group.visibility,
        member_count=await crud_group.count_group_members(db, group.uid),
        spot_count=await crud_group.count_group_spots(db, group.uid),
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get("", response_model=list[SpotGroupAdminListItem], summary="그룹 목록 조회")
async def list_groups(
    response: Response,
    start: int = Query(0, alias="_start", ge=0),
    end: int = Query(25, alias="_end", ge=0),
    sort: str = Query("uid", alias="_sort"),
    order: str = Query("asc", alias="_order"),
    name_like: str | None = Query(None),
    visibility: str | None = Query(None),
    user_uid: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[SpotGroupAdminListItem]:
    """멤버십과 무관하게 전체 그룹을 조회한다(PRIVATE 포함). name_like/visibility/user_uid로 필터할 수 있다."""
    if sort not in crud_group.SORTABLE_FIELDS:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"Not sortable: {sort}")
    items, total = await crud_group.list_groups_admin(
        db,
        offset=start,
        limit=max(end - start, 0),
        sort=sort,
        order=order.lower(),
        name_like=name_like,
        visibility=visibility,
        user_uid=user_uid,
    )
    response.headers["X-Total-Count"] = str(total)
    return [
        SpotGroupAdminListItem(
            uid=group.uid,
            name=group.name,
            visibility=group.visibility,
            member_count=member_count,
            spot_count=spot_count,
            created_at=group.created_at,
            updated_at=group.updated_at,
        )
        for group, member_count, spot_count in items
    ]


@router.get(
    "/{group_uid}", response_model=SpotGroupAdminDetail, summary="그룹 상세 조회"
)
async def get_group(
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> SpotGroupAdminDetail:
    """멤버십과 무관하게 조회할 수 있다(PRIVATE 그룹 포함)."""
    return await _to_admin_detail(db, group)


@router.patch(
    "/{group_uid}", response_model=SpotGroupAdminDetail, summary="그룹 정보 수정"
)
async def update_group(
    payload: SpotGroupUpdate,
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> SpotGroupAdminDetail:
    """name/description/visibility 중 전달된 필드만 수정한다."""
    group = await crud_group.update_group(
        db, group, payload.model_dump(exclude_unset=True)
    )
    return await _to_admin_detail(db, group)


@router.delete(
    "/{group_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="그룹 삭제",
)
async def delete_group(
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> None:
    """그룹과 소속 멤버·스팟 관계를 모두 삭제하는 비가역 작업이라 MANAGER 이상만 실행할 수 있다."""
    await crud_group.delete_group(db, group)


@router.get(
    "/{group_uid}/members",
    response_model=list[SpotGroupAdminMemberOut],
    summary="그룹 멤버 목록 조회",
)
async def list_group_members(
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> list[SpotGroupAdminMemberOut]:
    """멤버십과 무관하게 조회할 수 있다. 사용자 nickname/email을 함께 반환한다."""
    rows = await crud_group.list_members_admin(db, group.uid)
    return [
        SpotGroupAdminMemberOut(
            user_uid=member.user_uid,
            nickname=user.nickname,
            email=user.email,
            role=member.role,
            invited_by_uid=member.invited_by_uid,
            created_at=member.created_at,
        )
        for member, user in rows
    ]


@router.post(
    "/{group_uid}/members",
    response_model=SpotGroupAdminMemberOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="멤버 강제 추가",
)
async def add_group_member(
    payload: SpotGroupMemberInvite,
    staff: CurrentStaff,
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> SpotGroupAdminMemberOut:
    """앱 API와 달리 PRIVATE 그룹에도 강제 추가 가능하다(지원/모더레이션 목적). 임의 유저에게 role을 부여할 수 있어 MANAGER 이상만 실행할 수 있다."""
    target = await crud_user.get_user_by_id(db, payload.user_uid)
    if target is None:
        raise AppException(ErrorCode.USER_NOT_FOUND, "User not found")

    member = await crud_group.add_member(
        db,
        group_uid=group.uid,
        user_uid=target.uid,
        role=payload.role,
        invited_by_uid=staff.uid,
    )
    return SpotGroupAdminMemberOut(
        user_uid=member.user_uid,
        nickname=target.nickname,
        email=target.email,
        role=member.role,
        invited_by_uid=member.invited_by_uid,
        created_at=member.created_at,
    )


@router.patch(
    "/{group_uid}/members/{user_uid}",
    response_model=SpotGroupAdminMemberOut,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="멤버 역할 변경",
)
async def update_group_member_role(
    user_uid: str,
    payload: SpotGroupMemberRoleUpdate,
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> SpotGroupAdminMemberOut:
    """임의 사용자에게 owner를 포함한 role을 강제로 부여할 수 있어 MANAGER 이상만 실행할 수 있다. 그룹에 남은 유일한 owner는 강등할 수 없다."""
    target = await crud_group.get_membership(db, group.uid, user_uid)
    if target is None:
        raise AppException(ErrorCode.SPOT_GROUP_MEMBER_NOT_FOUND, "Member not found")
    member = await crud_group.update_member_role(db, target, payload.role)
    user = await crud_user.get_user_by_id(db, member.user_uid)
    return SpotGroupAdminMemberOut(
        user_uid=member.user_uid,
        nickname=user.nickname,
        email=user.email,
        role=member.role,
        invited_by_uid=member.invited_by_uid,
        created_at=member.created_at,
    )


@router.delete(
    "/{group_uid}/members/{user_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="멤버 추방",
)
async def remove_group_member(
    user_uid: str,
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> None:
    """MANAGER 이상만 실행할 수 있다. 그룹에 남은 유일한 owner는 제거할 수 없다."""
    target = await crud_group.get_membership(db, group.uid, user_uid)
    if target is None:
        raise AppException(ErrorCode.SPOT_GROUP_MEMBER_NOT_FOUND, "Member not found")
    await crud_group.remove_member(db, target)


@router.get(
    "/{group_uid}/spots",
    response_model=list[SpotGroupSpotItem],
    summary="그룹 스팟 목록 조회",
)
async def list_group_spots(
    group: SpotGroup = Depends(_get_group_or_404),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[SpotGroupSpotItem]:
    """멤버십과 무관하게 조회할 수 있다."""
    rows = await crud_group.list_group_spots(db, group.uid, offset=offset, limit=limit)
    thumbnails = await crud_image.get_thumbnails_by_spots(
        db, [spot.uid for spot, _ in rows]
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


@router.delete(
    "/{group_uid}/spots/{spot_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="그룹 스팟 제거",
)
async def remove_group_spot(
    spot_uid: str,
    group: SpotGroup = Depends(_get_group_or_404),
    db: AsyncSession = Depends(get_db),
) -> None:
    """멤버십과 무관하게 제거할 수 있다(모더레이션 목적)."""
    removed = await crud_group.remove_spot(db, group.uid, spot_uid)
    if not removed:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not in this group")
