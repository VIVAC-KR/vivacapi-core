from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import bearer, make_user
from vivacapi.core.security import create_access_token
from vivacapi.crud import spot_review as crud_review
from vivacapi.models.spot import PipelineStatus, Spot
from vivacapi.models.user import StaffRole


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


async def _make_staff(db: AsyncSession, suffix: str, role: StaffRole = StaffRole.STAFF):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"staff-sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user, create_access_token(user.uid)


# ---------------------------------------------------------------------------
# POST /v1/explore/spots/{uid}/reviews — create
# ---------------------------------------------------------------------------


async def test_create_review_unauthenticated_returns_401(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    response = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews", json={"rating": 8}
    )
    assert response.status_code == 401


async def test_create_review_succeeds(db_client: AsyncClient, db_session: AsyncSession):
    spot = await _make_spot(db_session)
    user, token = await _make_auth_user(db_session, "create1")

    response = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews",
        json={"rating": 8, "content": "좋아요"},
        headers=bearer(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 8
    assert body["user_uid"] == user.uid
    assert body["nickname"] == user.nickname


async def test_create_duplicate_review_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    _, token = await _make_auth_user(db_session, "dup1")
    await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews",
        json={"rating": 5},
        headers=bearer(token),
    )

    response = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews",
        json={"rating": 7},
        headers=bearer(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEW_ALREADY_EXISTS"


async def test_create_review_rejects_rating_above_10(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    _, token = await _make_auth_user(db_session, "range1")

    response = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews",
        json={"rating": 11},
        headers=bearer(token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH/DELETE /v1/explore/spots/{uid}/reviews/{uid} — 본인/staff 권한
# ---------------------------------------------------------------------------


async def test_update_review_forbidden_for_non_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    owner, owner_token = await _make_auth_user(db_session, "own1")
    _, stranger_token = await _make_auth_user(db_session, "str1")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=owner.uid, rating=5, content=None
    )

    response = await db_client.patch(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}",
        json={"rating": 9},
        headers=bearer(stranger_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_update_review_succeeds_for_owner(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    owner, owner_token = await _make_auth_user(db_session, "own2")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=owner.uid, rating=5, content=None
    )

    response = await db_client.patch(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}",
        json={"rating": 9},
        headers=bearer(owner_token),
    )

    assert response.status_code == 200
    assert response.json()["rating"] == 9


async def test_delete_review_forbidden_for_staff_below_manager(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    owner, _ = await _make_auth_user(db_session, "own3")
    staff, staff_token = await _make_staff(db_session, "s1", StaffRole.STAFF)
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=owner.uid, rating=5, content=None
    )

    response = await db_client.delete(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}",
        headers=bearer(staff_token),
    )

    assert response.status_code == 403


async def test_delete_review_succeeds_for_manager(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    owner, _ = await _make_auth_user(db_session, "own4")
    staff, staff_token = await _make_staff(db_session, "s2", StaffRole.MANAGER)
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=owner.uid, rating=5, content=None
    )

    response = await db_client.delete(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}",
        headers=bearer(staff_token),
    )

    assert response.status_code == 204

    list_response = await db_client.get(f"/v1/explore/spots/{spot.uid}/reviews")
    assert list_response.json() == []


async def test_delete_review_succeeds_for_owner_and_allows_rereview(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    owner, owner_token = await _make_auth_user(db_session, "own5")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=owner.uid, rating=5, content=None
    )

    delete_response = await db_client.delete(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}",
        headers=bearer(owner_token),
    )
    assert delete_response.status_code == 204

    recreate_response = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews",
        json={"rating": 3},
        headers=bearer(owner_token),
    )
    assert recreate_response.status_code == 201


# ---------------------------------------------------------------------------
# POST /v1/explore/spots/{uid}/reviews/{uid}/reports — 신고
# ---------------------------------------------------------------------------


async def test_report_own_review_forbidden(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    owner, owner_token = await _make_auth_user(db_session, "rep1")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=owner.uid, rating=5, content=None
    )

    response = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}/reports",
        json={"reason": "내 리뷰"},
        headers=bearer(owner_token),
    )

    assert response.status_code == 403


async def test_report_review_succeeds_then_duplicate_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session)
    owner, _ = await _make_auth_user(db_session, "rep2")
    reporter, reporter_token = await _make_auth_user(db_session, "rep2-reporter")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=owner.uid, rating=5, content=None
    )

    first = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}/reports",
        json={"reason": "부적절한 내용"},
        headers=bearer(reporter_token),
    )
    assert first.status_code == 204

    second = await db_client.post(
        f"/v1/explore/spots/{spot.uid}/reviews/{review.uid}/reports",
        json={"reason": "또 신고"},
        headers=bearer(reporter_token),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "REVIEW_REPORT_ALREADY_EXISTS"
