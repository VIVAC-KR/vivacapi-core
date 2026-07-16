from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import bearer, make_user
from vivacapi.core.security import create_access_token
from vivacapi.crud import spot_group as crud_group
from vivacapi.models.spot_group import GroupRole, GroupVisibility
from vivacapi.models.user import User


async def _make_auth_user(db: AsyncSession, suffix: str) -> tuple[User, str]:
    user = await make_user(
        db, email=f"{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    return user, create_access_token(user.uid)


# ---------------------------------------------------------------------------
# POST /v1/invites — 생성
# ---------------------------------------------------------------------------


async def test_create_general_invite_succeeds(
    db_client: AsyncClient, db_session: AsyncSession
):
    _, token = await _make_auth_user(db_session, "inv-gen1")

    response = await db_client.post("/v1/invites", json={}, headers=bearer(token))

    assert response.status_code == 201
    body = response.json()
    assert body["group_uid"] is None
    assert body["group_role"] is None
    assert body["status"] == "pending"


async def test_create_invite_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.post("/v1/invites", json={})
    assert response.status_code == 401


async def test_create_group_invite_as_owner_succeeds(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, token = await _make_auth_user(db_session, "inv-own1")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group A",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )

    response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "editor"},
        headers=bearer(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["group_uid"] == group.uid
    assert body["group_role"] == "editor"


async def test_create_group_invite_missing_role_returns_422(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, token = await _make_auth_user(db_session, "inv-own2")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group B",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )

    response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_create_group_invite_as_non_owner_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, _ = await _make_auth_user(db_session, "inv-own3")
    editor, editor_token = await _make_auth_user(db_session, "inv-editor1")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group C",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=editor.uid,
        role=GroupRole.EDITOR,
        invited_by_uid=owner.uid,
    )

    response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "viewer"},
        headers=bearer(editor_token),
    )
    assert response.status_code == 403


async def test_create_group_invite_for_private_group_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, token = await _make_auth_user(db_session, "inv-own4")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group D",
        description=None,
        visibility=GroupVisibility.PRIVATE,
    )

    response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "viewer"},
        headers=bearer(token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SPOT_GROUP_INVITE_NOT_ALLOWED"


async def test_create_invite_for_nonexistent_group_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    _, token = await _make_auth_user(db_session, "inv-none1")

    response = await db_client.post(
        "/v1/invites",
        json={"group_uid": "nonexistent0000000000", "group_role": "viewer"},
        headers=bearer(token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/invites/{uid} — 미리보기 (비로그인 허용)
# ---------------------------------------------------------------------------


async def test_preview_invite_succeeds_without_auth(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, token = await _make_auth_user(db_session, "inv-prev1")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group E",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )
    create_response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "viewer"},
        headers=bearer(token),
    )
    invite_uid = create_response.json()["uid"]

    response = await db_client.get(f"/v1/invites/{invite_uid}")

    assert response.status_code == 200
    body = response.json()
    assert body["inviter_nickname"] == owner.nickname
    assert body["group_name"] == "Group E"
    assert body["status"] == "pending"


async def test_preview_nonexistent_invite_returns_404(db_client: AsyncClient):
    response = await db_client.get("/v1/invites/nonexistent0000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVITE_NOT_FOUND"


# ---------------------------------------------------------------------------
# POST /v1/invites/{uid}/accept — 기존 로그인 유저의 그룹 초대 수락
# ---------------------------------------------------------------------------


async def test_accept_group_invite_adds_membership(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "inv-acc1")
    invitee, invitee_token = await _make_auth_user(db_session, "inv-acc1-invitee")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group F",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )
    create_response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "editor"},
        headers=bearer(owner_token),
    )
    invite_uid = create_response.json()["uid"]

    response = await db_client.post(
        f"/v1/invites/{invite_uid}/accept", headers=bearer(invitee_token)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    membership = await crud_group.get_membership(db_session, group.uid, invitee.uid)
    assert membership is not None
    assert GroupRole(membership.role) == GroupRole.EDITOR
    assert membership.invited_by_uid == owner.uid


async def test_accept_already_accepted_invite_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "inv-acc2")
    invitee, invitee_token = await _make_auth_user(db_session, "inv-acc2-invitee")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group G",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )
    create_response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "viewer"},
        headers=bearer(owner_token),
    )
    invite_uid = create_response.json()["uid"]
    await db_client.post(
        f"/v1/invites/{invite_uid}/accept", headers=bearer(invitee_token)
    )

    second_invitee, second_token = await _make_auth_user(db_session, "inv-acc2-second")
    response = await db_client.post(
        f"/v1/invites/{invite_uid}/accept", headers=bearer(second_token)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVITE_NOT_ACCEPTABLE"


async def test_accept_general_referral_invite_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    _, inviter_token = await _make_auth_user(db_session, "inv-acc3")
    _, invitee_token = await _make_auth_user(db_session, "inv-acc3-invitee")
    create_response = await db_client.post(
        "/v1/invites", json={}, headers=bearer(inviter_token)
    )
    invite_uid = create_response.json()["uid"]

    response = await db_client.post(
        f"/v1/invites/{invite_uid}/accept", headers=bearer(invitee_token)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVITE_NOT_ACCEPTABLE"


async def test_accept_invite_for_existing_member_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "inv-acc4")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group H",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )
    create_response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "viewer"},
        headers=bearer(owner_token),
    )
    invite_uid = create_response.json()["uid"]

    # owner는 이미 그룹 멤버(OWNER) 상태
    response = await db_client.post(
        f"/v1/invites/{invite_uid}/accept", headers=bearer(owner_token)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SPOT_GROUP_MEMBER_ALREADY_EXISTS"


# ---------------------------------------------------------------------------
# POST /v1/auth/google — 신규 가입 시 invite_uid 자동 소비
# ---------------------------------------------------------------------------


async def test_signup_with_group_invite_joins_group_and_sets_referrer(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    owner, owner_token = await _make_auth_user(db_session, "inv-signup1")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="Group I",
        description=None,
        visibility=GroupVisibility.PUBLIC,
    )
    create_response = await db_client.post(
        "/v1/invites",
        json={"group_uid": group.uid, "group_role": "contributor"},
        headers=bearer(owner_token),
    )
    invite_uid = create_response.json()["uid"]

    fake_idinfo: dict[str, Any] = {
        "sub": "google-sub-invitee-1",
        "email": "invitee1@example.com",
        "name": "Invitee",
    }
    monkeypatch.setattr(
        "vivacapi.api.v1.endpoints.auth.verify_google_id_token", lambda _t: fake_idinfo
    )

    response = await db_client.post(
        "/v1/auth/google", json={"id_token": "fake", "invite_uid": invite_uid}
    )
    assert response.status_code == 200

    from sqlalchemy import select

    result = await db_session.execute(
        select(User).where(User.google_sub == "google-sub-invitee-1")
    )
    new_user = result.scalar_one()
    assert new_user.referred_by_uid == owner.uid

    membership = await crud_group.get_membership(db_session, group.uid, new_user.uid)
    assert membership is not None
    assert GroupRole(membership.role) == GroupRole.CONTRIBUTOR


async def test_signup_with_general_referral_invite_sets_referrer_only(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    inviter, inviter_token = await _make_auth_user(db_session, "inv-signup2")
    create_response = await db_client.post(
        "/v1/invites", json={}, headers=bearer(inviter_token)
    )
    invite_uid = create_response.json()["uid"]

    fake_idinfo: dict[str, Any] = {
        "sub": "google-sub-invitee-2",
        "email": "invitee2@example.com",
        "name": "Invitee2",
    }
    monkeypatch.setattr(
        "vivacapi.api.v1.endpoints.auth.verify_google_id_token", lambda _t: fake_idinfo
    )

    response = await db_client.post(
        "/v1/auth/google", json={"id_token": "fake", "invite_uid": invite_uid}
    )
    assert response.status_code == 200

    from sqlalchemy import select

    result = await db_session.execute(
        select(User).where(User.google_sub == "google-sub-invitee-2")
    )
    new_user = result.scalar_one()
    assert new_user.referred_by_uid == inviter.uid


async def test_signup_with_invalid_invite_uid_still_succeeds(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_idinfo: dict[str, Any] = {
        "sub": "google-sub-invitee-3",
        "email": "invitee3@example.com",
        "name": "Invitee3",
    }
    monkeypatch.setattr(
        "vivacapi.api.v1.endpoints.auth.verify_google_id_token", lambda _t: fake_idinfo
    )

    response = await db_client.post(
        "/v1/auth/google",
        json={"id_token": "fake", "invite_uid": "nonexistent0000000000"},
    )
    assert response.status_code == 200

    from sqlalchemy import select

    result = await db_session.execute(
        select(User).where(User.google_sub == "google-sub-invitee-3")
    )
    new_user = result.scalar_one()
    assert new_user.referred_by_uid is None


async def test_existing_user_login_with_invite_uid_does_not_consume(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    existing = await make_user(
        db_session, email="existing-inv@example.com", google_sub="sub-existing-inv"
    )
    inviter, inviter_token = await _make_auth_user(db_session, "inv-signup4")
    create_response = await db_client.post(
        "/v1/invites", json={}, headers=bearer(inviter_token)
    )
    invite_uid = create_response.json()["uid"]

    fake_idinfo: dict[str, Any] = {
        "sub": "sub-existing-inv",
        "email": "existing-inv@example.com",
        "name": "Existing",
    }
    monkeypatch.setattr(
        "vivacapi.api.v1.endpoints.auth.verify_google_id_token", lambda _t: fake_idinfo
    )

    response = await db_client.post(
        "/v1/auth/google", json={"id_token": "fake", "invite_uid": invite_uid}
    )
    assert response.status_code == 200

    await db_session.refresh(existing)
    assert existing.referred_by_uid is None
