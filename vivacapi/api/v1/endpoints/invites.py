from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import get_current_user
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import invite as crud_invite
from vivacapi.crud import spot_group as crud_group
from vivacapi.crud import user as crud_user
from vivacapi.models.spot_group import GroupRole, GroupVisibility
from vivacapi.models.user import User
from vivacapi.schemas.invite import InviteCreate, InvitePreview, InviteResponse

router = APIRouter()


@router.post(
    "",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="초대 링크 생성",
)
async def create_invite(
    payload: InviteCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """1회용 초대 링크를 발급한다. group_uid/group_role을 함께 주면 그룹
    초대(발급자가 해당 그룹 owner여야 함, PRIVATE 그룹은 초대 불가), 둘
    다 비우면 일반 앱 리퍼럴 링크가 된다. 발급자가 그룹 멤버가 아니면
    존재를 숨기기 위해 403 대신 404를 반환한다."""
    if payload.group_uid is not None:
        group = await crud_group.get_group_by_uid(session, payload.group_uid)
        if group is None:
            raise AppException(ErrorCode.SPOT_GROUP_NOT_FOUND, "Group not found")
        if group.visibility == GroupVisibility.PRIVATE:
            raise AppException(
                ErrorCode.SPOT_GROUP_INVITE_NOT_ALLOWED,
                "PRIVATE 그룹은 멤버를 초대할 수 없습니다. visibility를 먼저 변경하세요.",
            )
        # 존재를 숨기려고 멤버가 아니면 403이 아닌 404를 쓴다 (spot_groups.py와 동일 패턴).
        membership = await crud_group.get_membership(session, group.uid, user.uid)
        if membership is None:
            raise AppException(ErrorCode.SPOT_GROUP_NOT_FOUND, "Group not found")
        if GroupRole(membership.role) != GroupRole.OWNER:
            raise AppException(ErrorCode.FORBIDDEN, "owner 권한이 필요합니다")

    invite = await crud_invite.create_invite(
        session,
        inviter_uid=user.uid,
        group_uid=payload.group_uid,
        group_role=payload.group_role,
    )
    return InviteResponse.model_validate(invite)


@router.get("/{uid}", response_model=InvitePreview, summary="초대 링크 미리보기")
async def preview_invite(
    uid: str,
    session: AsyncSession = Depends(get_db),
) -> InvitePreview:
    """로그인 전에도 열람 가능한 초대장 미리보기 — 초대한 사람 닉네임, 그룹
    초대라면 그룹명, 초대 상태(pending/accepted/revoked)를 반환한다."""
    invite = await crud_invite.get_invite_by_uid(session, uid)
    if invite is None:
        raise AppException(ErrorCode.INVITE_NOT_FOUND, "Invite not found")

    inviter = await crud_user.get_user_by_id(session, invite.inviter_uid)
    group = (
        await crud_group.get_group_by_uid(session, invite.group_uid)
        if invite.group_uid
        else None
    )
    return InvitePreview(
        inviter_nickname=inviter.nickname if inviter else "알 수 없음",
        group_name=group.name if group else None,
        status=invite.status,
    )


@router.post("/{uid}/accept", response_model=InviteResponse, summary="초대 링크 수락")
async def accept_invite(
    uid: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """이미 가입된 유저가 그룹 초대 링크를 열었을 때 사용한다(신규 가입자는
    /auth/google이 자동으로 처리하므로 이 엔드포인트를 거치지 않는다).
    이미 수락/폐기됐거나 그룹 초대가 아니면 409 INVITE_NOT_ACCEPTABLE."""
    invite = await crud_invite.get_invite_by_uid(session, uid)
    if invite is None:
        raise AppException(ErrorCode.INVITE_NOT_FOUND, "Invite not found")

    invite = await crud_invite.accept_invite(session, invite, user.uid)
    return InviteResponse.model_validate(invite)
