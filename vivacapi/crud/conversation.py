from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud.user_block import has_block_between
from vivacapi.models.conversation import (
    Conversation,
    ConversationParticipant,
    ConversationType,
)
from vivacapi.models.message import Message


async def get_or_create_direct_conversation(
    session: AsyncSession, *, user_uid: str, target_uid: str
) -> Conversation:
    """같은 두 유저의 DIRECT 대화가 이미 있으면 재사용하고, 없으면 새로 만든다."""
    if user_uid == target_uid:
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "자기 자신과의 DM은 만들 수 없습니다"
        )
    if await has_block_between(session, user_uid, target_uid):
        raise AppException(
            ErrorCode.USER_BLOCKED, "차단 관계가 있어 대화를 시작할 수 없습니다"
        )

    p1 = aliased(ConversationParticipant)
    p2 = aliased(ConversationParticipant)
    existing = await session.execute(
        select(Conversation)
        .join(p1, p1.conversation_uid == Conversation.uid)
        .join(p2, p2.conversation_uid == Conversation.uid)
        .where(
            Conversation.type == ConversationType.DIRECT,
            p1.user_uid == user_uid,
            p2.user_uid == target_uid,
        )
    )
    conversation = existing.scalar_one_or_none()
    if conversation is not None:
        return conversation

    conversation = Conversation(type=ConversationType.DIRECT)
    session.add(conversation)
    await session.flush()
    session.add_all(
        [
            ConversationParticipant(
                conversation_uid=conversation.uid, user_uid=user_uid
            ),
            ConversationParticipant(
                conversation_uid=conversation.uid, user_uid=target_uid
            ),
        ]
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def create_group_conversation(
    session: AsyncSession,
    *,
    creator_uid: str,
    participant_uids: list[str],
    name: str | None,
) -> Conversation:
    members = {creator_uid, *participant_uids}
    conversation = Conversation(type=ConversationType.GROUP, name=name)
    session.add(conversation)
    await session.flush()
    session.add_all(
        ConversationParticipant(conversation_uid=conversation.uid, user_uid=uid)
        for uid in members
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def get_conversation_by_uid(
    session: AsyncSession, uid: str
) -> Conversation | None:
    result = await session.execute(select(Conversation).where(Conversation.uid == uid))
    return result.scalar_one_or_none()


async def get_active_participant(
    session: AsyncSession, conversation_uid: str, user_uid: str
) -> ConversationParticipant | None:
    result = await session.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_uid == conversation_uid,
            ConversationParticipant.user_uid == user_uid,
            ConversationParticipant.left_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def list_active_participant_uids(
    session: AsyncSession, conversation_uid: str
) -> list[str]:
    result = await session.execute(
        select(ConversationParticipant.user_uid).where(
            ConversationParticipant.conversation_uid == conversation_uid,
            ConversationParticipant.left_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def list_conversations_for_user(
    session: AsyncSession, user_uid: str, *, offset: int, limit: int
) -> list[tuple[Conversation, ConversationParticipant]]:
    stmt = (
        select(Conversation, ConversationParticipant)
        .join(
            ConversationParticipant,
            ConversationParticipant.conversation_uid == Conversation.uid,
        )
        .where(
            ConversationParticipant.user_uid == user_uid,
            ConversationParticipant.left_at.is_(None),
        )
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(conversation, participant) for conversation, participant in result.all()]


async def get_unread_counts(
    session: AsyncSession, user_uid: str, participants: list[ConversationParticipant]
) -> dict[str, int]:
    """참여자별 last_read_at 기준으로 안읽은 메시지 수를 DB에서 집계한다."""
    conversation_uids = [participant.conversation_uid for participant in participants]
    if not conversation_uids:
        return {}
    stmt = (
        select(Message.conversation_uid, func.count())
        .select_from(Message)
        .join(
            ConversationParticipant,
            (ConversationParticipant.conversation_uid == Message.conversation_uid)
            & (ConversationParticipant.user_uid == user_uid),
        )
        .where(
            Message.conversation_uid.in_(conversation_uids),
            Message.sender_uid != user_uid,
            Message.deleted_at.is_(None),
            or_(
                ConversationParticipant.last_read_at.is_(None),
                Message.created_at > ConversationParticipant.last_read_at,
            ),
        )
        .group_by(Message.conversation_uid)
    )
    result = await session.execute(stmt)
    counts = {uid: 0 for uid in conversation_uids}
    counts.update(dict(result.all()))
    return counts


async def mark_read(
    session: AsyncSession, participant: ConversationParticipant
) -> ConversationParticipant:
    participant.last_read_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(participant)
    return participant
