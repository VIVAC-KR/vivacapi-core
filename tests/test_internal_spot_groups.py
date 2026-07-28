from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import bearer, make_user
from vivacapi.core.security import create_access_token
from vivacapi.crud import spot_group as crud_group
from vivacapi.models.spot import PipelineStatus, Spot
from vivacapi.models.spot_group import GroupRole
from vivacapi.models.user import StaffRole


async def _make_staff(db: AsyncSession, suffix: str, role: StaffRole = StaffRole.STAFF):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user


async def _make_spot(
    db: AsyncSession, title: str = "Spot", *, deleted: bool = False
) -> Spot:
    spot = Spot(
        title=title,
        rating_avg=0.0,
        review_count=0,
        pipeline_status=PipelineStatus.PUBLISHED,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def _make_group(db: AsyncSession, suffix: str, visibility: str = "private"):
    owner = await make_user(
        db, email=f"owner-{suffix}@example.com", google_sub=f"owner-sub-{suffix}"
    )
    group = await crud_group.create_group(
        db,
        owner_uid=owner.uid,
        name=f"그룹-{suffix}",
        description=None,
        visibility=visibility,
    )
    return group, owner


# ---------------------------------------------------------------------------
# 라우터 단위 인증 게이트
# ---------------------------------------------------------------------------


async def test_list_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/groups")
    assert response.status_code == 401


async def test_list_non_staff_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    user = await make_user(
        db_session, email="notstaff@example.com", google_sub="notstaff-sub"
    )
    token = create_access_token(user.uid)

    response = await db_client.get("/v1/internal/groups", headers=bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# GET /v1/internal/groups — 목록/상세, 멤버십 무관
# ---------------------------------------------------------------------------


async def test_staff_can_list_any_groups_with_total_count_header(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "list1")
    token = create_access_token(staff.uid)
    await _make_group(db_session, "a", visibility="private")
    await _make_group(db_session, "b", visibility="public")

    response = await db_client.get("/v1/internal/groups", headers=bearer(token))

    assert response.status_code == 200
    assert int(response.headers["X-Total-Count"]) >= 2


async def test_staff_can_view_group_without_membership(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "view1")
    token = create_access_token(staff.uid)
    group, _ = await _make_group(db_session, "priv", visibility="private")

    response = await db_client.get(
        f"/v1/internal/groups/{group.uid}", headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json()["member_count"] == 1


async def test_list_sort_whitelist_rejects_unknown_field(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "sort1")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/groups?_sort=not_a_field", headers=bearer(token)
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /v1/internal/groups/{uid} — STAFF로 충분
# ---------------------------------------------------------------------------


async def test_staff_can_update_group_metadata(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "upd1")
    token = create_access_token(staff.uid)
    group, _ = await _make_group(db_session, "upd", visibility="public")

    response = await db_client.patch(
        f"/v1/internal/groups/{group.uid}",
        json={"visibility": "private"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["visibility"] == "private"


# ---------------------------------------------------------------------------
# DELETE /v1/internal/groups/{uid} — MANAGER 이상
# ---------------------------------------------------------------------------


async def test_delete_group_forbidden_for_staff_role(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "del1", role=StaffRole.STAFF)
    token = create_access_token(staff.uid)
    group, _ = await _make_group(db_session, "del1")

    response = await db_client.delete(
        f"/v1/internal/groups/{group.uid}", headers=bearer(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_delete_group_succeeds_for_manager(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "del2", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)
    group, _ = await _make_group(db_session, "del2")

    response = await db_client.delete(
        f"/v1/internal/groups/{group.uid}", headers=bearer(token)
    )

    assert response.status_code == 204
    assert await crud_group.get_group_by_uid(db_session, group.uid) is None


async def test_delete_nonexistent_group_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "del3", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)

    response = await db_client.delete(
        "/v1/internal/groups/doesnotexist12345678", headers=bearer(token)
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 멤버 강제 관리 — MANAGER 이상, PRIVATE 그룹에도 강제 추가 가능
# ---------------------------------------------------------------------------


async def test_add_member_forbidden_for_staff_role(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "mem1", role=StaffRole.STAFF)
    token = create_access_token(staff.uid)
    group, _ = await _make_group(db_session, "mem1")
    target = await make_user(
        db_session, email="target1@example.com", google_sub="target1-sub"
    )

    response = await db_client.post(
        f"/v1/internal/groups/{group.uid}/members",
        json={"user_uid": target.uid, "role": "viewer"},
        headers=bearer(token),
    )

    assert response.status_code == 403


async def test_manager_can_force_add_member_to_private_group(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "mem2", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)
    group, _ = await _make_group(db_session, "mem2", visibility="private")
    target = await make_user(
        db_session, email="target2@example.com", google_sub="target2-sub"
    )

    response = await db_client.post(
        f"/v1/internal/groups/{group.uid}/members",
        json={"user_uid": target.uid, "role": "editor"},
        headers=bearer(token),
    )

    assert response.status_code == 201
    assert response.json()["role"] == "editor"
    assert response.json()["nickname"] == target.nickname


async def test_manager_cannot_demote_last_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "mem3", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)
    group, owner = await _make_group(db_session, "mem3")

    response = await db_client.patch(
        f"/v1/internal/groups/{group.uid}/members/{owner.uid}",
        json={"role": "viewer"},
        headers=bearer(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SPOT_GROUP_LAST_OWNER_REQUIRED"


async def test_manager_can_remove_non_owner_member(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "mem4", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)
    group, owner = await _make_group(db_session, "mem4", visibility="invite_only")
    viewer = await make_user(
        db_session, email="viewer4@example.com", google_sub="viewer4-sub"
    )
    await crud_group.add_member(
        db_session,
        group_uid=group.uid,
        user_uid=viewer.uid,
        role=GroupRole.VIEWER,
        invited_by_uid=owner.uid,
    )

    response = await db_client.delete(
        f"/v1/internal/groups/{group.uid}/members/{viewer.uid}", headers=bearer(token)
    )

    assert response.status_code == 204
    assert await crud_group.get_membership(db_session, group.uid, viewer.uid) is None


# ---------------------------------------------------------------------------
# POST /v1/internal/groups — 그룹 생성, staff가 owner
# ---------------------------------------------------------------------------


async def test_create_group_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.post(
        "/v1/internal/groups", json={"name": "그룹", "visibility": "private"}
    )

    assert response.status_code == 401


async def test_staff_can_create_group_and_becomes_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "create1")
    token = create_access_token(staff.uid)

    response = await db_client.post(
        "/v1/internal/groups",
        json={"name": "새 그룹", "visibility": "private"},
        headers=bearer(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "새 그룹"
    assert body["member_count"] == 1

    membership = await crud_group.get_membership(db_session, body["uid"], staff.uid)
    assert membership is not None
    assert membership.role == GroupRole.OWNER


# ---------------------------------------------------------------------------
# POST /v1/internal/groups/{uid}/spots — 스팟 추가, pipeline_status 무관
# ---------------------------------------------------------------------------


async def test_staff_can_add_spot_to_group(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "spotadd1")
    token = create_access_token(staff.uid)
    group, _ = await _make_group(db_session, "spotadd1")
    spot = await _make_spot(db_session, "추가할 스팟")

    response = await db_client.post(
        f"/v1/internal/groups/{group.uid}/spots",
        json={"spot_uid": spot.uid},
        headers=bearer(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["uid"] == spot.uid
    assert body["added_by_uid"] == staff.uid


async def test_add_deleted_spot_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "spotadd2")
    token = create_access_token(staff.uid)
    group, _ = await _make_group(db_session, "spotadd2")
    spot = await _make_spot(db_session, "삭제된 스팟", deleted=True)

    response = await db_client.post(
        f"/v1/internal/groups/{group.uid}/spots",
        json={"spot_uid": spot.uid},
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_NOT_FOUND"


async def test_add_duplicate_spot_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "spotadd3")
    token = create_access_token(staff.uid)
    group, _ = await _make_group(db_session, "spotadd3")
    spot = await _make_spot(db_session, "중복 스팟")
    await crud_group.add_spot(
        db_session, group_uid=group.uid, spot_uid=spot.uid, added_by_uid=staff.uid
    )

    response = await db_client.post(
        f"/v1/internal/groups/{group.uid}/spots",
        json={"spot_uid": spot.uid},
        headers=bearer(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SPOT_GROUP_SPOT_ALREADY_EXISTS"


async def test_add_spot_unauthenticated_returns_401(
    db_client: AsyncClient, db_session: AsyncSession
):
    group, _ = await _make_group(db_session, "spotadd4")
    spot = await _make_spot(db_session, "인증 없음")

    response = await db_client.post(
        f"/v1/internal/groups/{group.uid}/spots",
        json={"spot_uid": spot.uid},
    )

    assert response.status_code == 401
