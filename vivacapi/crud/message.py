import base64
import json
from datetime import datetime, timezone

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.models.conversation import Conversation
from vivacapi.models.message import Message


def _encode_cursor(created_at: datetime, uid: str) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "u": uid}).encode()
    return base64.urlsafe_b64encode(payload).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["t"]), str(payload["u"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "Invalid cursor for messages"
        ) from exc


async def create_message(
    session: AsyncSession, *, conversation: Conversation, sender_uid: str, content: str
) -> Message:
    message = Message(
        conversation_uid=conversation.uid, sender_uid=sender_uid, content=content
    )
    session.add(message)
    # 대화 목록을 최근 활동순으로 보여주기 위해 새 메시지가 생기면 갱신한다.
    conversation.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(message)
    return message


async def list_messages(
    session: AsyncSession,
    conversation_uid: str,
    *,
    cursor: str | None = None,
    limit: int = 30,
) -> tuple[list[Message], str | None, bool]:
    """최신 메시지부터 역순으로 (created_at, uid) 키셋 페이지네이션한다."""
    stmt = select(Message).where(
        Message.conversation_uid == conversation_uid, Message.deleted_at.is_(None)
    )
    if cursor:
        last_created_at, last_uid = _decode_cursor(cursor)
        stmt = stmt.where(
            tuple_(Message.created_at, Message.uid) < tuple_(last_created_at, last_uid)
        )
    stmt = stmt.order_by(Message.created_at.desc(), Message.uid.desc()).limit(limit + 1)
    result = await session.execute(stmt)
    messages = list(result.scalars().all())

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    next_cursor = (
        _encode_cursor(messages[-1].created_at, messages[-1].uid) if has_more else None
    )
    return messages, next_cursor, has_more


async def get_last_messages(
    session: AsyncSession, conversation_uids: list[str]
) -> dict[str, Message]:
    """대화 목록 화면의 미리보기용 — 대화별 가장 최근 메시지 1건."""
    if not conversation_uids:
        return {}
    stmt = (
        select(Message)
        .distinct(Message.conversation_uid)
        .where(
            Message.conversation_uid.in_(conversation_uids),
            Message.deleted_at.is_(None),
        )
        .order_by(Message.conversation_uid, Message.created_at.desc())
    )
    result = await session.execute(stmt)
    return {message.conversation_uid: message for message in result.scalars().all()}


async def get_message_by_uid(session: AsyncSession, uid: str) -> Message | None:
    result = await session.execute(select(Message).where(Message.uid == uid))
    return result.scalar_one_or_none()


async def soft_delete_message(session: AsyncSession, message: Message) -> None:
    message.deleted_at = datetime.now(timezone.utc)
    await session.commit()
