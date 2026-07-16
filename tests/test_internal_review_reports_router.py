from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import bearer, make_user
from vivacapi.core.security import create_access_token
from vivacapi.crud import spot_review as crud_review
from vivacapi.crud import spot_review_report as crud_report
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


async def _make_staff(db: AsyncSession, suffix: str, role: StaffRole = StaffRole.STAFF):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"staff-sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user, create_access_token(user.uid)


async def test_list_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/review-reports")
    assert response.status_code == 401


async def test_list_non_staff_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    user = await make_user(
        db_session, email="notstaff@example.com", google_sub="notstaff-sub"
    )
    token = create_access_token(user.uid)

    response = await db_client.get("/v1/internal/review-reports", headers=bearer(token))

    assert response.status_code == 403


async def test_staff_can_list_reports_with_total_count(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff, token = await _make_staff(db_session, "list1", StaffRole.STAFF)
    spot = await _make_spot(db_session)
    reviewer = await make_user(
        db_session, email="reviewer@example.com", google_sub="reviewer-sub"
    )
    reporter = await make_user(
        db_session, email="reporter@example.com", google_sub="reporter-sub"
    )
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=reviewer.uid, rating=1, content="별로"
    )
    await crud_report.create_report(
        db_session,
        review_uid=review.uid,
        reporter_user_uid=reporter.uid,
        reason="욕설 포함",
    )

    response = await db_client.get("/v1/internal/review-reports", headers=bearer(token))

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"
    body = response.json()[0]
    assert body["reason"] == "욕설 포함"
    assert body["spot_uid"] == spot.uid
    assert body["reporter_nickname"] == reporter.nickname
    assert body["review_deleted"] is False


async def test_review_deleted_flag_reflects_soft_delete(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff, token = await _make_staff(db_session, "list2", StaffRole.STAFF)
    spot = await _make_spot(db_session)
    reviewer = await make_user(
        db_session, email="reviewer2@example.com", google_sub="reviewer2-sub"
    )
    reporter = await make_user(
        db_session, email="reporter2@example.com", google_sub="reporter2-sub"
    )
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=reviewer.uid, rating=1, content=None
    )
    await crud_report.create_report(
        db_session,
        review_uid=review.uid,
        reporter_user_uid=reporter.uid,
        reason="어뷰징",
    )
    await crud_review.soft_delete_review(db_session, review)

    response = await db_client.get(
        "/v1/internal/review-reports",
        params={"spot_uid": spot.uid},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()[0]["review_deleted"] is True
