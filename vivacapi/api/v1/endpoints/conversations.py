from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.api.v1.endpoints.summaries import (
    CREATE_CONVERSATION_SUMMARY,
    DELETE_MESSAGE_SUMMARY,
    GET_CONVERSATION_SUMMARY,
    LIST_CONVERSATIONS_SUMMARY,
    LIST_MESSAGES_SUMMARY,
    MARK_CONVERSATION_READ_SUMMARY,
    SEND_MESSAGE_SUMMARY,
)
from vivacapi.core.database import get_db
from vivacapi.core.deps import get_current_user
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.limits import rate_limit
from vivacapi.core.ws_manager import manager
from vivacapi.crud import conversation as crud_conversation
from vivacapi.crud import message as crud_message
from vivacapi.crud import user as crud_user
from vivacapi.crud import user_block as crud_block
from vivacapi.models.conversation import (
    Conversation,
    ConversationParticipant,
    ConversationType,
)
from vivacapi.models.message import Message
from vivacapi.models.user import User
from vivacapi.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationListItem,
)
from vivacapi.schemas.message import MessageCreate, MessageListResponse, MessageOut

router = APIRouter()


async def _get_conversation_or_404(
    conversation_uid: str, session: AsyncSession = Depends(get_db)
) -> Conversation:
    conversation = await crud_conversation.get_conversation_by_uid(
        session, conversation_uid
    )
    if conversation is None:
        raise AppException(ErrorCode.CONVERSATION_NOT_FOUND, "Conversation not found")
    return conversation


async def _get_active_participant_or_404(
    conversation: Conversation = Depends(_get_conversation_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> tuple[Conversation, ConversationParticipant]:
    """참여자가 아니면 존재를 숨기기 위해 403 대신 404를 반환한다(spot_groups.py와 동일 패턴)."""
    participant = await crud_conversation.get_active_participant(
        session, conversation.uid, user.uid
    )
    if participant is None:
        raise AppException(ErrorCode.CONVERSATION_NOT_FOUND, "Conversation not found")
    return conversation, participant


def _to_message_out(message: Message) -> MessageOut:
    return MessageOut(
        uid=message.uid,
        conversation_uid=message.conversation_uid,
        sender_uid=message.sender_uid,
        content=message.content,
        created_at=message.created_at,
    )


async def _to_detail(
    session: AsyncSession, conversation: Conversation
) -> ConversationDetail:
    participant_uids = await crud_conversation.list_active_participant_uids(
        session, conversation.uid
    )
    return ConversationDetail(
        uid=conversation.uid,
        type=conversation.type,
        name=conversation.name,
        participant_uids=participant_uids,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.post(
    "",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
    summary=CREATE_CONVERSATION_SUMMARY,
)
async def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    """type=direct면 participant_uids는 상대방 1명만 지정한다(기존 DIRECT 대화가
    있으면 재사용, 차단 관계가 있으면 403 USER_BLOCKED). type=group이면 여러 명을
    지정할 수 있고 요청자가 자동으로 포함된다."""
    if payload.type == ConversationType.DIRECT:
        if len(payload.participant_uids) != 1:
            raise AppException(
                ErrorCode.VALIDATION_ERROR, "DIRECT 대화는 상대방 1명만 지정해야 합니다"
            )
        target_uid = payload.participant_uids[0]
        if await crud_user.get_user_by_id(session, target_uid) is None:
            raise AppException(ErrorCode.USER_NOT_FOUND, "User not found")
        conversation = await crud_conversation.get_or_create_direct_conversation(
            session, user_uid=user.uid, target_uid=target_uid
        )
    else:
        for target_uid in payload.participant_uids:
            if await crud_user.get_user_by_id(session, target_uid) is None:
                raise AppException(ErrorCode.USER_NOT_FOUND, "User not found")
        conversation = await crud_conversation.create_group_conversation(
            session,
            creator_uid=user.uid,
            participant_uids=payload.participant_uids,
            name=payload.name,
        )
    return await _to_detail(session, conversation)


@router.get(
    "", response_model=list[ConversationListItem], summary=LIST_CONVERSATIONS_SUMMARY
)
async def list_conversations(
    user: User = Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationListItem]:
    """최근 활동순으로 내 대화 목록을 반환한다. 각 항목에 마지막 메시지 미리보기와
    안읽은 메시지 수가 포함된다."""
    rows = await crud_conversation.list_conversations_for_user(
        session, user.uid, offset=offset, limit=limit
    )
    conversation_uids = [conversation.uid for conversation, _ in rows]
    last_messages = await crud_message.get_last_messages(session, conversation_uids)
    unread_counts = await crud_conversation.get_unread_counts(
        session, user.uid, [participant for _, participant in rows]
    )

    items = []
    for conversation, _participant in rows:
        last_message = last_messages.get(conversation.uid)
        items.append(
            ConversationListItem(
                uid=conversation.uid,
                type=conversation.type,
                name=conversation.name,
                last_message_preview=last_message.content if last_message else None,
                last_message_at=last_message.created_at if last_message else None,
                unread_count=unread_counts.get(conversation.uid, 0),
                updated_at=conversation.updated_at,
            )
        )
    return items


@router.get(
    "/{conversation_uid}",
    response_model=ConversationDetail,
    summary=GET_CONVERSATION_SUMMARY,
)
async def get_conversation(
    conversation_and_participant: tuple[
        Conversation, ConversationParticipant
    ] = Depends(_get_active_participant_or_404),
    session: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    conversation, _ = conversation_and_participant
    return await _to_detail(session, conversation)


@router.get(
    "/{conversation_uid}/messages",
    response_model=MessageListResponse,
    summary=LIST_MESSAGES_SUMMARY,
)
async def list_messages(
    conversation_and_participant: tuple[
        Conversation, ConversationParticipant
    ] = Depends(_get_active_participant_or_404),
    cursor: str | None = Query(None, description="이전 응답의 next_cursor 값"),
    limit: int = Query(30, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    """최신 메시지부터 역순으로 반환한다."""
    conversation, _ = conversation_and_participant
    messages, next_cursor, has_more = await crud_message.list_messages(
        session, conversation.uid, cursor=cursor, limit=limit
    )
    return MessageListResponse(
        items=[_to_message_out(message) for message in messages],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post(
    "/{conversation_uid}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary=SEND_MESSAGE_SUMMARY,
    dependencies=[Depends(rate_limit("dm_message_send", times=60, seconds=60))],
)
async def send_message(
    payload: MessageCreate,
    conversation_and_participant: tuple[
        Conversation, ConversationParticipant
    ] = Depends(_get_active_participant_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageOut:
    """DIRECT 대화는 상대와 차단 관계가 있으면(양방향) 전송이 거부된다. 저장 후
    온라인 상태인 다른 참여자에게 WebSocket으로 즉시 push한다."""
    conversation, _ = conversation_and_participant
    participant_uids = await crud_conversation.list_active_participant_uids(
        session, conversation.uid
    )

    if conversation.type == ConversationType.DIRECT:
        other_uids = [uid for uid in participant_uids if uid != user.uid]
        if other_uids and await crud_block.has_block_between(
            session, user.uid, other_uids[0]
        ):
            raise AppException(
                ErrorCode.USER_BLOCKED, "차단 관계가 있어 메시지를 보낼 수 없습니다"
            )

    message = await crud_message.create_message(
        session, conversation=conversation, sender_uid=user.uid, content=payload.content
    )
    message_out = _to_message_out(message)
    for uid in participant_uids:
        if uid != user.uid:
            await manager.send_to_user(
                uid, {"type": "message", "data": message_out.model_dump(mode="json")}
            )
    return message_out


@router.post(
    "/{conversation_uid}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=MARK_CONVERSATION_READ_SUMMARY,
)
async def mark_conversation_read(
    conversation_and_participant: tuple[
        Conversation, ConversationParticipant
    ] = Depends(_get_active_participant_or_404),
    session: AsyncSession = Depends(get_db),
) -> None:
    _, participant = conversation_and_participant
    await crud_conversation.mark_read(session, participant)


@router.delete(
    "/{conversation_uid}/messages/{message_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=DELETE_MESSAGE_SUMMARY,
)
async def delete_message(
    message_uid: str,
    conversation_and_participant: tuple[
        Conversation, ConversationParticipant
    ] = Depends(_get_active_participant_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """본인이 보낸 메시지만 삭제(soft delete)할 수 있다."""
    conversation, _ = conversation_and_participant
    message = await crud_message.get_message_by_uid(session, message_uid)
    if (
        message is None
        or message.conversation_uid != conversation.uid
        or message.deleted_at is not None
    ):
        raise AppException(ErrorCode.MESSAGE_NOT_FOUND, "Message not found")
    if message.sender_uid != user.uid:
        raise AppException(ErrorCode.FORBIDDEN, "본인 메시지만 삭제할 수 있습니다")
    await crud_message.soft_delete_message(session, message)
