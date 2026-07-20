from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot_group as crud_group
from vivacapi.models.invite import Invite, InviteStatus
from vivacapi.models.spot_group import GroupRole
from vivacapi.models.user import User


async def create_invite(
    session: AsyncSession,
    *,
    inviter_uid: str,
    group_uid: str | None = None,
    group_role: GroupRole | None = None,
) -> Invite:
    invite = Invite(inviter_uid=inviter_uid, group_uid=group_uid, group_role=group_role)
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


async def get_invite_by_uid(session: AsyncSession, uid: str) -> Invite | None:
    result = await session.execute(select(Invite).where(Invite.uid == uid))
    return result.scalar_one_or_none()


async def accept_invite(session: AsyncSession, invite: Invite, user_uid: str) -> Invite:
    """이미 가입된 유저가 초대 링크를 열었을 때 그룹에 합류시킨다."""
    if invite.status != InviteStatus.PENDING or invite.group_uid is None:
        raise AppException(
            ErrorCode.INVITE_NOT_ACCEPTABLE, "This invite can no longer be accepted"
        )

    await crud_group.add_member(
        session,
        group_uid=invite.group_uid,
        user_uid=user_uid,
        role=invite.group_role,
        invited_by_uid=invite.inviter_uid,
    )

    invite.status = InviteStatus.ACCEPTED
    invite.accepted_by_uid = user_uid
    invite.accepted_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(invite)
    return invite


async def consume_invite_for_signup(
    session: AsyncSession, invite_uid: str, new_user: User
) -> None:
    """신규 가입 시 초대 링크를 자동 수락한다. 초대가 유효하지 않으면 조용히 무시한다."""
    invite = await get_invite_by_uid(session, invite_uid)
    if invite is None or invite.status != InviteStatus.PENDING:
        return

    new_user.referred_by_uid = invite.inviter_uid

    # group_uid가 없는 일반 리퍼럴 초대는 status를 ACCEPTED로 전환하지 않는다 —
    # PENDING을 유지해 같은 링크로 여러 명이 반복 가입할 수 있게 한다(재사용 링크).
    # 그룹 초대는 기존과 동일하게 1회용으로 소진한다.
    if invite.group_uid is not None:
        await crud_group.add_member(
            session,
            group_uid=invite.group_uid,
            user_uid=new_user.uid,
            role=invite.group_role,
            invited_by_uid=invite.inviter_uid,
        )
        invite.status = InviteStatus.ACCEPTED
        invite.accepted_by_uid = new_user.uid
        invite.accepted_at = datetime.now(timezone.utc)

    await session.commit()
