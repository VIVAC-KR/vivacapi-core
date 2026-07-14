from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import bearer, make_user
from vivacapi.core.security import create_access_token
from vivacapi.crud import spot_group as crud_group
from vivacapi.models.spot import PipelineStatus, Spot
from vivacapi.models.spot_group import GroupRole


async def _make_spot(db: AsyncSession, title: str = "Spot") -> Spot:
    spot = Spot(
        title=title,
        rating_avg=0.0,
        review_count=0,
        pipeline_status=PipelineStatus.PUBLISHED,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def _make_auth_user(db: AsyncSession, suffix: str):
    user = await make_user(
        db, email=f"{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    return user, create_access_token(user.uid)


# ---------------------------------------------------------------------------
# POST /v1/groups — create
# ---------------------------------------------------------------------------


async def test_create_group_sets_creator_as_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    user, token = await _make_auth_user(db_session, "creator")

    response = await db_client.post(
        "/v1/groups",
        json={"name": "내 캠핑지 모음", "visibility": "private"},
        headers=bearer(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["my_role"] == "owner"
    assert body["spot_count"] == 0
    assert body["visibility"] == "private"


async def test_create_group_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.post("/v1/groups", json={"name": "x"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/groups/{uid} — visibility gating
# ---------------------------------------------------------------------------


async def test_private_group_hidden_from_non_member(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "priv-owner")
    stranger, stranger_token = await _make_auth_user(db_session, "priv-stranger")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="비공개",
        description=None,
        visibility="private",
    )

    response = await db_client.get(
        f"/v1/groups/{group.uid}", headers=bearer(stranger_token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_GROUP_NOT_FOUND"


async def test_public_group_readable_without_login(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, _ = await _make_auth_user(db_session, "pub-owner")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="공개",
        description=None,
        visibility="public",
    )

    response = await db_client.get(f"/v1/groups/{group.uid}")

    assert response.status_code == 200
    body = response.json()
    assert body["my_role"] is None


async def test_get_group_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    response = await db_client.get("/v1/groups/doesnotexist12345678")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_GROUP_NOT_FOUND"


# ---------------------------------------------------------------------------
# PATCH /v1/groups/{uid} — role gate (EDITOR+)
# ---------------------------------------------------------------------------


async def test_update_group_forbidden_for_viewer(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, _ = await _make_auth_user(db_session, "upd-owner")
    viewer, viewer_token = await _make_auth_user(db_session, "upd-viewer")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="invite_only",
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=viewer.uid,
        role=GroupRole.VIEWER,
        invited_by_uid=owner.uid,
    )

    response = await db_client.patch(
        f"/v1/groups/{group.uid}",
        json={"name": "새 이름"},
        headers=bearer(viewer_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_update_group_succeeds_for_editor(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, _ = await _make_auth_user(db_session, "upd2-owner")
    editor, editor_token = await _make_auth_user(db_session, "upd2-editor")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="invite_only",
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=editor.uid,
        role=GroupRole.EDITOR,
        invited_by_uid=owner.uid,
    )

    response = await db_client.patch(
        f"/v1/groups/{group.uid}",
        json={"name": "새 이름"},
        headers=bearer(editor_token),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "새 이름"


# ---------------------------------------------------------------------------
# POST/DELETE /v1/groups/{uid}/spots — CONTRIBUTOR can add, EDITOR can remove
# ---------------------------------------------------------------------------


async def test_contributor_can_add_but_not_remove_spot(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, _ = await _make_auth_user(db_session, "spot-owner")
    contributor, contributor_token = await _make_auth_user(db_session, "spot-contrib")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="invite_only",
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=contributor.uid,
        role=GroupRole.CONTRIBUTOR,
        invited_by_uid=owner.uid,
    )
    spot = await _make_spot(db_session)

    add_response = await db_client.post(
        f"/v1/groups/{group.uid}/spots",
        json={"spot_uid": spot.uid},
        headers=bearer(contributor_token),
    )
    assert add_response.status_code == 201
    assert add_response.json()["uid"] == spot.uid

    remove_response = await db_client.delete(
        f"/v1/groups/{group.uid}/spots/{spot.uid}", headers=bearer(contributor_token)
    )
    assert remove_response.status_code == 403


async def test_add_duplicate_spot_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "dup-owner")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="private",
    )
    spot = await _make_spot(db_session)
    await crud_group.add_spot(
        db_session, group_uid=group.uid, spot_uid=spot.uid, added_by_uid=owner.uid
    )

    response = await db_client.post(
        f"/v1/groups/{group.uid}/spots",
        json={"spot_uid": spot.uid},
        headers=bearer(owner_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SPOT_GROUP_SPOT_ALREADY_EXISTS"


# ---------------------------------------------------------------------------
# 멤버 초대/역할 관리 — OWNER 전용, PRIVATE 그룹은 초대 불가
# ---------------------------------------------------------------------------


async def test_invite_blocked_on_private_group(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "inv-owner")
    invitee, _ = await _make_auth_user(db_session, "inv-target")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="private",
    )

    response = await db_client.post(
        f"/v1/groups/{group.uid}/members",
        json={"user_uid": invitee.uid, "role": "viewer"},
        headers=bearer(owner_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SPOT_GROUP_INVITE_NOT_ALLOWED"


async def test_invite_as_owner_allows_co_ownership(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "coown-owner")
    invitee, _ = await _make_auth_user(db_session, "coown-target")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="invite_only",
    )

    response = await db_client.post(
        f"/v1/groups/{group.uid}/members",
        json={"user_uid": invitee.uid, "role": "owner"},
        headers=bearer(owner_token),
    )

    assert response.status_code == 201
    assert response.json()["role"] == "owner"


async def test_invite_forbidden_for_editor(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, _ = await _make_auth_user(db_session, "inv2-owner")
    editor, editor_token = await _make_auth_user(db_session, "inv2-editor")
    invitee, _ = await _make_auth_user(db_session, "inv2-target")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="invite_only",
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=editor.uid,
        role=GroupRole.EDITOR,
        invited_by_uid=owner.uid,
    )

    response = await db_client.post(
        f"/v1/groups/{group.uid}/members",
        json={"user_uid": invitee.uid, "role": "viewer"},
        headers=bearer(editor_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_cannot_demote_last_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "last-owner")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="private",
    )

    response = await db_client.patch(
        f"/v1/groups/{group.uid}/members/{owner.uid}",
        json={"role": "editor"},
        headers=bearer(owner_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SPOT_GROUP_LAST_OWNER_REQUIRED"


async def test_cannot_remove_last_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "last-owner-rm")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="private",
    )

    response = await db_client.delete(
        f"/v1/groups/{group.uid}/members/{owner.uid}", headers=bearer(owner_token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SPOT_GROUP_LAST_OWNER_REQUIRED"


async def test_second_owner_can_be_demoted(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "twoowner-a")
    co_owner, _ = await _make_auth_user(db_session, "twoowner-b")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="invite_only",
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=co_owner.uid,
        role=GroupRole.OWNER,
        invited_by_uid=owner.uid,
    )

    response = await db_client.patch(
        f"/v1/groups/{group.uid}/members/{co_owner.uid}",
        json={"role": "editor"},
        headers=bearer(owner_token),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "editor"


# ---------------------------------------------------------------------------
# DELETE /v1/groups/{uid} — OWNER 전용
# ---------------------------------------------------------------------------


async def test_delete_group_forbidden_for_editor(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, _ = await _make_auth_user(db_session, "del-owner")
    editor, editor_token = await _make_auth_user(db_session, "del-editor")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="invite_only",
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=editor.uid,
        role=GroupRole.EDITOR,
        invited_by_uid=owner.uid,
    )

    response = await db_client.delete(
        f"/v1/groups/{group.uid}", headers=bearer(editor_token)
    )

    assert response.status_code == 403


async def test_delete_group_succeeds_for_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner, owner_token = await _make_auth_user(db_session, "del2-owner")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="private",
    )

    response = await db_client.delete(
        f"/v1/groups/{group.uid}", headers=bearer(owner_token)
    )

    assert response.status_code == 204
    assert await crud_group.get_group_by_uid(db_session, group.uid) is None
