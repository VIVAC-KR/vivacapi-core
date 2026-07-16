from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import bearer, make_user
from vivacapi.core.security import create_access_token
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_group as crud_group
from vivacapi.models.spot import PipelineStatus, Spot
from vivacapi.models.user import StaffRole


async def _make_staff(db: AsyncSession, suffix: str, role: StaffRole = StaffRole.STAFF):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user


async def _make_spot(db: AsyncSession, title: str = "Spot", **kwargs) -> Spot:
    spot = Spot(
        title=title,
        rating_avg=kwargs.pop("rating_avg", 0.0),
        review_count=kwargs.pop("review_count", 0),
        pipeline_status=kwargs.pop("pipeline_status", PipelineStatus.PUBLISHED),
        **kwargs,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# ---------------------------------------------------------------------------
# DELETE /v1/internal/spots/{uid} — MANAGER 이상
# ---------------------------------------------------------------------------


async def test_delete_spot_forbidden_for_staff_below_manager(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "del1", StaffRole.STAFF)
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)

    response = await db_client.delete(
        f"/v1/internal/spots/{spot.uid}", headers=bearer(token)
    )

    assert response.status_code == 403


async def test_delete_spot_succeeds_for_manager_and_hides_from_explore(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "del2", StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)

    response = await db_client.delete(
        f"/v1/internal/spots/{spot.uid}", headers=bearer(token)
    )
    assert response.status_code == 204

    detail = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert detail.status_code == 404

    listing = await db_client.get("/v1/explore/spots")
    assert listing.json()["items"] == []


async def test_deleted_spot_hidden_from_admin_list_unless_included(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "del3", StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "삭제될 유니크스팟제목")
    await db_client.delete(f"/v1/internal/spots/{spot.uid}", headers=bearer(token))

    # title_like로 스코프를 좁혀 DB에 이미 있던 다른 row와 무관하게 검증한다.
    default_list = await db_client.get(
        "/v1/internal/spots",
        params={"title_like": "유니크스팟제목"},
        headers=bearer(token),
    )
    assert spot.uid not in [item["uid"] for item in default_list.json()]

    with_deleted = await db_client.get(
        "/v1/internal/spots",
        params={"title_like": "유니크스팟제목", "include_deleted": True},
        headers=bearer(token),
    )
    matching = [item for item in with_deleted.json() if item["uid"] == spot.uid]
    assert len(matching) == 1
    assert matching[0]["deleted_at"] is not None


async def test_deleted_spot_hidden_from_group_spot_list(db_session: AsyncSession):
    owner = await make_user(
        db_session, email="group-owner@example.com", google_sub="group-owner-sub"
    )
    spot = await _make_spot(db_session, "그룹에 담긴 스팟")
    group = await crud_group.create_group(
        db_session,
        owner_uid=owner.uid,
        name="그룹",
        description=None,
        visibility="private",
    )
    await crud_group.add_spot(
        db_session, group_uid=group.uid, spot_uid=spot.uid, added_by_uid=owner.uid
    )

    await crud_spot.delete_spot(db_session, spot)

    rows = await crud_group.list_group_spots(db_session, group.uid, offset=0, limit=20)
    assert rows == []


# ---------------------------------------------------------------------------
# POST /v1/internal/spots/{uid}/restore — MANAGER 이상
# ---------------------------------------------------------------------------


async def test_restore_spot_forbidden_for_staff_below_manager(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "res1", StaffRole.MANAGER)
    manager_token = create_access_token(manager.uid)
    staff = await _make_staff(db_session, "res1b", StaffRole.STAFF)
    staff_token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)
    await db_client.delete(
        f"/v1/internal/spots/{spot.uid}", headers=bearer(manager_token)
    )

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/restore", headers=bearer(staff_token)
    )

    assert response.status_code == 403


async def test_restore_spot_succeeds_and_reappears_in_explore(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "res2", StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)
    await db_client.delete(f"/v1/internal/spots/{spot.uid}", headers=bearer(token))

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/restore", headers=bearer(token)
    )
    assert response.status_code == 200
    assert response.json()["deleted_at"] is None

    detail = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert detail.status_code == 200
