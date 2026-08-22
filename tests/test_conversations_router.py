from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import bearer, make_user
from vivacapi.core.security import create_access_token
from vivacapi.crud import conversation as crud_conversation
from vivacapi.crud import user_block as crud_block


async def _make_auth_user(db: AsyncSession, suffix: str):
    user = await make_user(
        db, email=f"{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    return user, create_access_token(user.uid)


# ---------------------------------------------------------------------------
# POST /v1/conversations — create
# ---------------------------------------------------------------------------


async def test_create_direct_conversation(
    db_client: AsyncClient, db_session: AsyncSession
):
    user, token = await _make_auth_user(db_session, "creator")
    target, _ = await _make_auth_user(db_session, "target")

    response = await db_client.post(
        "/v1/conversations",
        json={"type": "direct", "participant_uids": [target.uid]},
        headers=bearer(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "direct"
    assert sorted(body["participant_uids"]) == sorted([user.uid, target.uid])


async def test_create_direct_conversation_unauthenticated_returns_401(
    db_client: AsyncClient,
):
    response = await db_client.post(
        "/v1/conversations", json={"type": "direct", "participant_uids": ["x"]}
    )
    assert response.status_code == 401


async def test_create_direct_conversation_with_multiple_targets_rejected(
    db_client: AsyncClient, db_session: AsyncSession
):
    _, token = await _make_auth_user(db_session, "multi")
    t1, _ = await _make_auth_user(db_session, "multi-t1")
    t2, _ = await _make_auth_user(db_session, "multi-t2")

    response = await db_client.post(
        "/v1/conversations",
        json={"type": "direct", "participant_uids": [t1.uid, t2.uid]},
        headers=bearer(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_direct_conversation_blocked_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    user, token = await _make_auth_user(db_session, "blk-user")
    target, _ = await _make_auth_user(db_session, "blk-target")
    await crud_block.block_user(
        db_session, blocker_uid=target.uid, blocked_uid=user.uid
    )

    response = await db_client.post(
        "/v1/conversations",
        json={"type": "direct", "participant_uids": [target.uid]},
        headers=bearer(token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_BLOCKED"


async def test_create_group_conversation(
    db_client: AsyncClient, db_session: AsyncSession
):
    user, token = await _make_auth_user(db_session, "grp-owner")
    m1, _ = await _make_auth_user(db_session, "grp-m1")
    m2, _ = await _make_auth_user(db_session, "grp-m2")

    response = await db_client.post(
        "/v1/conversations",
        json={
            "type": "group",
            "participant_uids": [m1.uid, m2.uid],
            "name": "여행방",
        },
        headers=bearer(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "group"
    assert body["name"] == "여행방"
    assert sorted(body["participant_uids"]) == sorted([user.uid, m1.uid, m2.uid])


# ---------------------------------------------------------------------------
# 참여자 아닌 유저 접근 차단
# ---------------------------------------------------------------------------


async def test_non_participant_gets_404_on_conversation(
    db_client: AsyncClient, db_session: AsyncSession
):
    a, _ = await _make_auth_user(db_session, "np-a")
    b, _ = await _make_auth_user(db_session, "np-b")
    stranger, stranger_token = await _make_auth_user(db_session, "np-stranger")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )

    response = await db_client.get(
        f"/v1/conversations/{conversation.uid}", headers=bearer(stranger_token)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_conversation_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    _, token = await _make_auth_user(db_session, "nf")
    response = await db_client.get(
        "/v1/conversations/doesnotexist12345678", headers=bearer(token)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


# ---------------------------------------------------------------------------
# 메시지 전송/조회/읽음 처리
# ---------------------------------------------------------------------------


async def test_send_and_list_messages(db_client: AsyncClient, db_session: AsyncSession):
    a, token_a = await _make_auth_user(db_session, "msg-a")
    b, token_b = await _make_auth_user(db_session, "msg-b")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )

    send_response = await db_client.post(
        f"/v1/conversations/{conversation.uid}/messages",
        json={"content": "안녕!"},
        headers=bearer(token_a),
    )
    assert send_response.status_code == 201
    assert send_response.json()["content"] == "안녕!"
    assert send_response.json()["sender_uid"] == a.uid

    list_response = await db_client.get(
        f"/v1/conversations/{conversation.uid}/messages", headers=bearer(token_b)
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["content"] == "안녕!"


async def test_send_message_blocked_direct_conversation_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    a, token_a = await _make_auth_user(db_session, "sb-a")
    b, _ = await _make_auth_user(db_session, "sb-b")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    # 대화 생성 후 상대가 나를 차단한 상황(기존 대화에도 소급 적용).
    await crud_block.block_user(db_session, blocker_uid=b.uid, blocked_uid=a.uid)

    response = await db_client.post(
        f"/v1/conversations/{conversation.uid}/messages",
        json={"content": "여전히 대화중?"},
        headers=bearer(token_a),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_BLOCKED"


async def test_send_message_non_participant_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    a, _ = await _make_auth_user(db_session, "sp-a")
    b, _ = await _make_auth_user(db_session, "sp-b")
    stranger, stranger_token = await _make_auth_user(db_session, "sp-stranger")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )

    response = await db_client.post(
        f"/v1/conversations/{conversation.uid}/messages",
        json={"content": "몰래 끼어들기"},
        headers=bearer(stranger_token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_mark_conversation_read(db_client: AsyncClient, db_session: AsyncSession):
    a, token_a = await _make_auth_user(db_session, "read-a")
    b, token_b = await _make_auth_user(db_session, "read-b")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    await db_client.post(
        f"/v1/conversations/{conversation.uid}/messages",
        json={"content": "읽어줘"},
        headers=bearer(token_b),
    )

    list_before = await db_client.get("/v1/conversations", headers=bearer(token_a))
    item_before = next(i for i in list_before.json() if i["uid"] == conversation.uid)
    assert item_before["unread_count"] == 1

    read_response = await db_client.post(
        f"/v1/conversations/{conversation.uid}/read", headers=bearer(token_a)
    )
    assert read_response.status_code == 204

    list_after = await db_client.get("/v1/conversations", headers=bearer(token_a))
    item_after = next(i for i in list_after.json() if i["uid"] == conversation.uid)
    assert item_after["unread_count"] == 0
    assert item_after["last_message_preview"] == "읽어줘"


async def test_delete_message_by_sender(
    db_client: AsyncClient, db_session: AsyncSession
):
    a, token_a = await _make_auth_user(db_session, "del-a")
    b, token_b = await _make_auth_user(db_session, "del-b")
    conversation = await crud_conversation.get_or_create_direct_conversation(
        db_session, user_uid=a.uid, target_uid=b.uid
    )
    send_response = await db_client.post(
        f"/v1/conversations/{conversation.uid}/messages",
        json={"content": "실수로 보냄"},
        headers=bearer(token_a),
    )
    message_uid = send_response.json()["uid"]

    forbidden = await db_client.delete(
        f"/v1/conversations/{conversation.uid}/messages/{message_uid}",
        headers=bearer(token_b),
    )
    assert forbidden.status_code == 403

    ok = await db_client.delete(
        f"/v1/conversations/{conversation.uid}/messages/{message_uid}",
        headers=bearer(token_a),
    )
    assert ok.status_code == 204

    list_response = await db_client.get(
        f"/v1/conversations/{conversation.uid}/messages", headers=bearer(token_a)
    )
    assert list_response.json()["items"] == []


# ---------------------------------------------------------------------------
# POST/DELETE /v1/users/{uid}/block
# ---------------------------------------------------------------------------


async def test_block_and_unblock_user(db_client: AsyncClient, db_session: AsyncSession):
    a, token_a = await _make_auth_user(db_session, "bu-a")
    b, _ = await _make_auth_user(db_session, "bu-b")

    block_response = await db_client.post(
        f"/v1/users/{b.uid}/block", headers=bearer(token_a)
    )
    assert block_response.status_code == 204

    # DIRECT 생성이 차단으로 막히는지로 반영 확인.
    create_response = await db_client.post(
        "/v1/conversations",
        json={"type": "direct", "participant_uids": [b.uid]},
        headers=bearer(token_a),
    )
    assert create_response.status_code == 403

    unblock_response = await db_client.delete(
        f"/v1/users/{b.uid}/block", headers=bearer(token_a)
    )
    assert unblock_response.status_code == 204

    create_response_2 = await db_client.post(
        "/v1/conversations",
        json={"type": "direct", "participant_uids": [b.uid]},
        headers=bearer(token_a),
    )
    assert create_response_2.status_code == 201


async def test_block_self_returns_422(db_client: AsyncClient, db_session: AsyncSession):
    a, token_a = await _make_auth_user(db_session, "bs-a")
    response = await db_client.post(f"/v1/users/{a.uid}/block", headers=bearer(token_a))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
