from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import make_user
from vivacapi.core.errors import AppException
from vivacapi.crud import conversation as crud_conversation
from vivacapi.crud import message as crud_message
from vivacapi.crud import user_block as crud_block
from vivacapi.models.conversation import ConversationType
from vivacapi.models.message import Message

# ---------------------------------------------------------------------------
# get_or_create_direct_conversation — 재사용/차단/자기자신
# ---------------------------------------------------------------------------


async def test_direct_conversation_is_reused(db_session: AsyncSession):
    a = await make_user(db_session, email="a@example.com", google_sub="sub-a")
    b = await make_user(db_session, email="b@example.com", google_sub="sub-b")

    first = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    second = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=b.uid, target_uid=a.uid
    )

    assert first.uid == second.uid
    assert first.type == ConversationType.DIRECT


async def test_direct_conversation_with_self_rejected(db_session: AsyncSession):
    a = await make_user(db_session, email="self@example.com", google_sub="sub-self")

    with pytest.raises(AppException) as excinfo:
        await crud_conversation.get_or_create_direct_conversation(
            db_session, user_uid=a.uid, target_uid=a.uid
        )
    assert excinfo.value.code.value == "VALIDATION_ERROR"


async def test_direct_conversation_blocked_by_target_rejected(db_session: AsyncSession):
    a = await make_user(
        db_session, email="blocker@example.com", google_sub="sub-blocker"
    )
    b = await make_user(
        db_session, email="blocked@example.com", google_sub="sub-blocked"
    )
    await crud_block.block_user(db_session, blocker_uid=b.uid, blocked_uid=a.uid)

    with pytest.raises(AppException) as excinfo:
        await crud_conversation.get_or_create_direct_conversation(
            db_session, user_uid=a.uid, target_uid=b.uid
        )
    assert excinfo.value.code.value == "USER_BLOCKED"


# ---------------------------------------------------------------------------
# create_group_conversation
# ---------------------------------------------------------------------------


async def test_group_conversation_includes_creator_and_dedupes(
    db_session: AsyncSession,
):
    creator = await make_user(db_session, email="gc@example.com", google_sub="sub-gc")
    member = await make_user(db_session, email="gm@example.com", google_sub="sub-gm")

    conversation = await crud_conversation.create_group_conversation(
        db_session,
        creator_uid=creator.uid,
        participant_uids=[member.uid, creator.uid],
        name="여행방",
    )

    uids = await crud_conversation.list_active_participant_uids(
        db_session, conversation.uid
    )
    assert sorted(uids) == sorted([creator.uid, member.uid])
    assert conversation.type == ConversationType.GROUP


# ---------------------------------------------------------------------------
# unread counts
# ---------------------------------------------------------------------------


async def test_unread_count_resets_after_mark_read(db_session: AsyncSession):
    a = await make_user(db_session, email="ua@example.com", google_sub="sub-ua")
    b = await make_user(db_session, email="ub@example.com", google_sub="sub-ub")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    await crud_message.create_message(
        db_session, conversation=conversation, sender_uid=b.uid, content="hi"
    )
    await crud_message.create_message(
        db_session, conversation=conversation, sender_uid=b.uid, content="there"
    )

    rows = await crud_conversation.list_conversations_for_user(
        db_session, a.uid, offset=0, limit=20
    )
    participants = [participant for _, participant in rows]
    counts = await crud_conversation.get_unread_counts(db_session, a.uid, participants)
    assert counts[conversation.uid] == 2

    participant = await crud_conversation.get_active_participant(
        db_session, conversation.uid, a.uid
    )
    await crud_conversation.mark_read(db_session, participant)

    rows = await crud_conversation.list_conversations_for_user(
        db_session, a.uid, offset=0, limit=20
    )
    participants = [participant for _, participant in rows]
    counts = await crud_conversation.get_unread_counts(db_session, a.uid, participants)
    assert counts[conversation.uid] == 0


async def test_own_messages_do_not_count_as_unread(db_session: AsyncSession):
    a = await make_user(db_session, email="oa@example.com", google_sub="sub-oa")
    b = await make_user(db_session, email="ob@example.com", google_sub="sub-ob")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    await crud_message.create_message(
        db_session, conversation=conversation, sender_uid=a.uid, content="hi"
    )

    participant = await crud_conversation.get_active_participant(
        db_session, conversation.uid, a.uid
    )
    counts = await crud_conversation.get_unread_counts(db_session, a.uid, [participant])
    assert counts[conversation.uid] == 0


# ---------------------------------------------------------------------------
# message pagination (keyset, 최신순)
# ---------------------------------------------------------------------------


async def test_list_messages_cursor_pagination(db_session: AsyncSession):
    a = await make_user(db_session, email="pa@example.com", google_sub="sub-pa")
    b = await make_user(db_session, email="pb@example.com", google_sub="sub-pb")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    # 같은 테스트 트랜잭션 안에서는 Postgres now()가 고정되어 crud.create_message로
    # 넣으면 모든 메시지의 created_at이 동일해진다 — 정렬을 검증하려면 시각을 직접
    # 벌려서 넣는다.
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        db_session.add(
            Message(
                conversation_uid=conversation.uid,
                sender_uid=a.uid,
                content=f"msg-{i}",
                created_at=base + timedelta(seconds=i),
            )
        )
    await db_session.commit()

    page1, cursor1, has_more1 = await crud_message.list_messages(
        db_session, conversation.uid, limit=3
    )
    assert [m.content for m in page1] == ["msg-4", "msg-3", "msg-2"]
    assert has_more1 is True
    assert cursor1 is not None

    page2, cursor2, has_more2 = await crud_message.list_messages(
        db_session, conversation.uid, cursor=cursor1, limit=3
    )
    assert [m.content for m in page2] == ["msg-1", "msg-0"]
    assert has_more2 is False
    assert cursor2 is None


async def test_soft_deleted_messages_excluded_from_list(db_session: AsyncSession):
    a = await make_user(db_session, email="da@example.com", google_sub="sub-da")
    b = await make_user(db_session, email="db@example.com", google_sub="sub-db")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    message = await crud_message.create_message(
        db_session, conversation=conversation, sender_uid=a.uid, content="삭제될 메시지"
    )
    await crud_message.soft_delete_message(db_session, message)

    messages, _, _ = await crud_message.list_messages(db_session, conversation.uid)
    assert messages == []


# ---------------------------------------------------------------------------
# user_block
# ---------------------------------------------------------------------------


async def test_block_user_is_idempotent(db_session: AsyncSession):
    a = await make_user(db_session, email="ba@example.com", google_sub="sub-ba")
    b = await make_user(db_session, email="bb@example.com", google_sub="sub-bb")

    first = await crud_block.block_user(
        db_session, blocker_uid=a.uid, blocked_uid=b.uid
    )
    second = await crud_block.block_user(
        db_session, blocker_uid=a.uid, blocked_uid=b.uid
    )
    assert first.blocked_uid == second.blocked_uid


async def test_has_block_between_checks_both_directions(db_session: AsyncSession):
    a = await make_user(db_session, email="dir-a@example.com", google_sub="sub-dir-a")
    b = await make_user(db_session, email="dir-b@example.com", google_sub="sub-dir-b")
    await crud_block.block_user(db_session, blocker_uid=b.uid, blocked_uid=a.uid)

    assert await crud_block.has_block_between(db_session, a.uid, b.uid) is True
    assert await crud_block.has_block_between(db_session, b.uid, a.uid) is True


async def test_unblock_user_is_idempotent(db_session: AsyncSession):
    a = await make_user(db_session, email="ua2@example.com", google_sub="sub-ua2")
    b = await make_user(db_session, email="ub2@example.com", google_sub="sub-ub2")

    # 차단한 적 없어도 에러 없이 통과해야 한다.
    await crud_block.unblock_user(db_session, blocker_uid=a.uid, blocked_uid=b.uid)

    await crud_block.block_user(db_session, blocker_uid=a.uid, blocked_uid=b.uid)
    await crud_block.unblock_user(db_session, blocker_uid=a.uid, blocked_uid=b.uid)
    assert await crud_block.has_block_between(db_session, a.uid, b.uid) is False
