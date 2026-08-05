from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot_group as crud_group
from vivacapi.models.invite import Invite, InviteStatus
from vivacapi.models.spot_group import GroupRole, GroupVisibility
from vivacapi.models.user import User

# 그룹 초대 링크 유효기간. created_at 기준으로 계산해 expires_at 컬럼을 두지 않는다
# (마이그레이션 없이 정책만 바꾸면 되고, 초대별 만료를 다르게 줄 이유가 아직 없다).
# ponytail: 전역 상수, 초대별 만료가 실제로 필요해지면 그때 컬럼을 추가한다.
GROUP_INVITE_TTL = timedelta(days=14)


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


async def is_group_invite_still_valid(session: AsyncSession, invite: Invite) -> bool:
    """발급 시점이 아니라 '수락 시점'의 권한 상태로 그룹 초대를 재검증한다.

    링크는 발급 후에도 계속 살아있으므로, 발급 당시 통과했던 조건이 그 사이
    깨졌을 수 있다. 재검증하지 않으면 강등/추방된 발급자가 남긴 링크가
    박제된 role을 계속 나눠주고, PRIVATE로 바뀐 그룹에도 계속 합류된다.
    """
    if invite.created_at is not None:
        # created_at은 timezone-aware(server_default now())지만, 방어적으로 naive면 UTC로 본다.
        created_at = invite.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created_at > GROUP_INVITE_TTL:
            return False

    group = await crud_group.get_group_by_uid(session, invite.group_uid)
    if group is None or group.visibility == GroupVisibility.PRIVATE:
        return False

    inviter_membership = await crud_group.get_membership(
        session, invite.group_uid, invite.inviter_uid
    )
    return (
        inviter_membership is not None
        and GroupRole(inviter_membership.role) == GroupRole.OWNER
    )


async def accept_invite(session: AsyncSession, invite: Invite, user_uid: str) -> Invite:
    """이미 가입된 유저가 초대 링크를 열었을 때 그룹에 합류시킨다."""
    if invite.status != InviteStatus.PENDING or invite.group_uid is None:
        raise AppException(
            ErrorCode.INVITE_NOT_ACCEPTABLE, "This invite can no longer be accepted"
        )

    if not await is_group_invite_still_valid(session, invite):
        raise AppException(
            ErrorCode.INVITE_NOT_ACCEPTABLE, "This invite is no longer valid"
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
    # 그룹 합류만 accept_invite와 동일한 수락 시점 재검증을 거친다 — 검증에 걸려도
    # 리퍼럴 귀속(referred_by_uid)은 그대로 두고 그룹 합류만 건너뛴다.
    if invite.group_uid is not None and await is_group_invite_still_valid(
        session, invite
    ):
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
