from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.security import create_access_token
from vivacapi.models.job import Job, JobStatus, JobType
from vivacapi.models.spot import Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo
from vivacapi.workers.handlers import HANDLERS
from tests.helpers import bearer, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(db: AsyncSession, suffix: str):
    user = await make_user(
        db, email=f"sbi-staff-{suffix}@example.com", google_sub=f"sbi-sub-{suffix}"
    )
    user.is_staff = True
    await db.commit()
    return user


async def _make_spot(
    db: AsyncSession, *, external_id: str, title: str = "Spot", source: str = "seed"
) -> Spot:
    spot = Spot(
        title=title,
        source=source,
        external_id=external_id,
        rating_avg=0.0,
        review_count=0,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def _post_bulk(
    client: AsyncClient, token: str, body: dict
) -> tuple[int, dict]:
    response = await client.post(
        "/v1/internal/spot-business-info/bulk", json=body, headers=bearer(token)
    )
    return response.status_code, response.json()


async def _run_pending_job(db: AsyncSession, job_id: str) -> Job:
    job = (await db.execute(select(Job).where(Job.uid == job_id))).scalar_one()
    handler = HANDLERS[JobType.SPOT_BUSINESS_INFO_BULK_UPSERT]
    result = await handler(db, job.payload)
    job.status = JobStatus.SUCCEEDED
    job.result = result
    await db.commit()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# POST /v1/internal/spot-business-info/bulk — auth / enqueue
# ---------------------------------------------------------------------------


async def test_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.post(
        "/v1/internal/spot-business-info/bulk",
        json={"rows": [{"spot_external_id": "x"}]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_non_staff_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    user = await make_user(
        db_session, email="sbi-user@example.com", google_sub="sbi-sub-user"
    )
    token = create_access_token(user.uid)

    response = await db_client.post(
        "/v1/internal/spot-business-info/bulk",
        json={"rows": [{"spot_external_id": "x"}]},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_staff_enqueue_returns_202_with_job_id(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "enqueue")
    token = create_access_token(staff.uid)

    status_code, body = await _post_bulk(
        db_client,
        token,
        {
            "rows": [
                {"spot_external_id": "ext-1", "business_type": "캠핑장"},
                {"spot_external_id": "ext-2"},
            ]
        },
    )

    assert status_code == 202
    job_id = body["job_id"]
    assert isinstance(job_id, str) and job_id

    job = (
        await db_session.execute(select(Job).where(Job.uid == job_id))
    ).scalar_one()
    assert job.type == JobType.SPOT_BUSINESS_INFO_BULK_UPSERT
    assert job.status == JobStatus.PENDING
    assert job.created_by == staff.uid
    assert len(job.payload["rows"]) == 2
    assert job.payload["dry_run"] is False


# ---------------------------------------------------------------------------
# Worker handler — insert / upsert / dry_run / mapping failure
# ---------------------------------------------------------------------------


async def test_handler_inserts_new_rows(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "insert")
    token = create_access_token(staff.uid)

    spot_a = await _make_spot(db_session, external_id="bi-ext-A", title="Camp A")
    spot_b = await _make_spot(db_session, external_id="bi-ext-B", title="Camp B")

    _, body = await _post_bulk(
        db_client,
        token,
        {
            "rows": [
                {
                    "spot_external_id": "bi-ext-A",
                    "business_reg_no": "111-22-33333",
                    "business_type": "캠핑장",
                    "operating_status": "운영",
                },
                {
                    "spot_external_id": "bi-ext-B",
                    "national_park_no": 7,
                    "licensed_at": "2024-01-15",
                },
            ]
        },
    )

    job = await _run_pending_job(db_session, body["job_id"])

    assert job.status == JobStatus.SUCCEEDED
    assert job.result == {
        "succeeded": 2,
        "failed": 0,
        "dry_run": False,
        "errors": [],
    }

    rows_by_spot = {
        r.spot_uid: r
        for r in (
            await db_session.execute(
                select(SpotBusinessInfo).where(
                    SpotBusinessInfo.spot_uid.in_([spot_a.uid, spot_b.uid])
                )
            )
        )
        .scalars()
        .all()
    }
    assert set(rows_by_spot.keys()) == {spot_a.uid, spot_b.uid}
    assert rows_by_spot[spot_a.uid].business_reg_no == "111-22-33333"
    assert rows_by_spot[spot_a.uid].operating_status == "운영"
    assert rows_by_spot[spot_b.uid].national_park_no == 7


async def test_handler_upserts_existing_rows(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "upsert")
    token = create_access_token(staff.uid)

    spot = await _make_spot(db_session, external_id="bi-ext-upsert")
    spot_uid = spot.uid
    existing = SpotBusinessInfo(
        spot_uid=spot_uid,
        business_type="기존 타입",
        operating_status="운영중지",
    )
    db_session.add(existing)
    await db_session.commit()
    original_uid = existing.uid

    _, body = await _post_bulk(
        db_client,
        token,
        {
            "rows": [
                {
                    "spot_external_id": "bi-ext-upsert",
                    "business_type": "캠핑장",
                    "operating_status": "운영",
                    "business_reg_no": "999-88-77777",
                }
            ]
        },
    )

    job = await _run_pending_job(db_session, body["job_id"])
    assert job.result["succeeded"] == 1
    assert job.result["failed"] == 0

    db_session.expire_all()
    rows = (
        await db_session.execute(
            select(SpotBusinessInfo).where(SpotBusinessInfo.spot_uid == spot_uid)
        )
    ).scalars().all()
    assert len(rows) == 1
    updated = rows[0]
    assert updated.uid == original_uid
    assert updated.business_type == "캠핑장"
    assert updated.operating_status == "운영"
    assert updated.business_reg_no == "999-88-77777"


async def test_handler_dry_run_does_not_persist(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "dryrun")
    token = create_access_token(staff.uid)

    spot_x = await _make_spot(db_session, external_id="bi-dry-X")
    spot_y = await _make_spot(db_session, external_id="bi-dry-Y")

    _, body = await _post_bulk(
        db_client,
        token,
        {
            "dry_run": True,
            "rows": [
                {"spot_external_id": "bi-dry-X", "business_type": "캠핑장"},
                {"spot_external_id": "bi-dry-Y", "business_type": "글램핑"},
            ],
        },
    )

    job = await _run_pending_job(db_session, body["job_id"])

    assert job.result == {
        "succeeded": 2,
        "failed": 0,
        "dry_run": True,
        "errors": [],
    }

    rows = (
        await db_session.execute(
            select(SpotBusinessInfo).where(
                SpotBusinessInfo.spot_uid.in_([spot_x.uid, spot_y.uid])
            )
        )
    ).scalars().all()
    assert rows == []


async def test_handler_mapping_failure_rolls_back_all(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "mapfail")
    token = create_access_token(staff.uid)

    spot_ok = await _make_spot(db_session, external_id="bi-mf-ok")

    _, body = await _post_bulk(
        db_client,
        token,
        {
            "rows": [
                {"spot_external_id": "bi-mf-ok", "business_type": "캠핑장"},
                {"spot_external_id": "bi-mf-missing", "business_type": "글램핑"},
            ]
        },
    )

    job = await _run_pending_job(db_session, body["job_id"])

    assert job.result["failed"] == 1
    assert job.result["succeeded"] == 0  # 전체 롤백
    assert job.result["dry_run"] is False
    assert len(job.result["errors"]) == 1
    err = job.result["errors"][0]
    assert err["index"] == 1
    assert "bi-mf-missing" in err["reason"]
    assert "not found" in err["reason"]

    rows = (
        await db_session.execute(
            select(SpotBusinessInfo).where(SpotBusinessInfo.spot_uid == spot_ok.uid)
        )
    ).scalars().all()
    assert rows == []
