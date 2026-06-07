import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.job import Job, JobStatus, JobType
from app.models.spot import Spot
from app.workers import spots_bulk as spots_bulk_module
from app.workers.handlers import HANDLERS
from tests.helpers import bearer, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(db: AsyncSession, suffix: str):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    await db.commit()
    return user


async def _post_bulk(
    client: AsyncClient, token: str, body: dict
) -> tuple[int, dict]:
    response = await client.post(
        "/v1/internal/spots/bulk", json=body, headers=bearer(token)
    )
    return response.status_code, response.json()


async def _run_pending_job(db: AsyncSession, job_id: str) -> Job:
    """테스트에서 워커 1사이클을 시뮬레이션: 핸들러를 직접 호출하고 결과를 기록."""
    job = (await db.execute(select(Job).where(Job.uid == job_id))).scalar_one()
    handler = HANDLERS[JobType.SPOTS_BULK_UPSERT]
    result = await handler(db, job.payload)
    job.status = JobStatus.SUCCEEDED
    job.result = result
    await db.commit()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# POST /v1/internal/spots/bulk — auth / enqueue
# ---------------------------------------------------------------------------


async def test_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.post(
        "/v1/internal/spots/bulk",
        json={"rows": [{"title": "A"}]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_non_staff_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    user = await make_user(
        db_session, email="user@example.com", google_sub="sub-user"
    )
    token = create_access_token(user.uid)

    response = await db_client.post(
        "/v1/internal/spots/bulk",
        json={"rows": [{"title": "A"}]},
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
                {"title": "Camp 1", "source": "seed", "external_id": "e-1"},
                {"title": "Camp 2"},
            ]
        },
    )

    assert status_code == 202
    job_id = body["job_id"]
    assert isinstance(job_id, str) and job_id

    job = (
        await db_session.execute(select(Job).where(Job.uid == job_id))
    ).scalar_one()
    assert job.type == JobType.SPOTS_BULK_UPSERT
    assert job.status == JobStatus.PENDING
    assert job.created_by == staff.uid
    assert len(job.payload["rows"]) == 2
    assert job.payload["dry_run"] is False


# ---------------------------------------------------------------------------
# Worker handler — insert / upsert / dry_run / partial failure
# ---------------------------------------------------------------------------


async def test_handler_inserts_new_rows(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "insert")
    token = create_access_token(staff.uid)

    _, body = await _post_bulk(
        db_client,
        token,
        {
            "rows": [
                {"title": "Camp A", "source": "seed", "external_id": "ext-A"},
                {"title": "Camp B", "source": "seed", "external_id": "ext-B"},
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

    spots = (
        await db_session.execute(
            select(Spot).where(Spot.source == "seed").order_by(Spot.external_id)
        )
    ).scalars().all()
    assert [s.title for s in spots] == ["Camp A", "Camp B"]


async def test_handler_upserts_existing_rows(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "upsert")
    token = create_access_token(staff.uid)

    existing = Spot(
        title="old title",
        source="seed",
        external_id="ext-upsert",
        rating_avg=1.0,
        review_count=0,
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
                    "title": "new title",
                    "source": "seed",
                    "external_id": "ext-upsert",
                    "address": "new address",
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
            select(Spot).where(
                Spot.source == "seed", Spot.external_id == "ext-upsert"
            )
        )
    ).scalars().all()
    # 행이 1개만 있어야 함 (insert가 아닌 update)
    assert len(rows) == 1
    updated = rows[0]
    # uid는 보존, 값은 업데이트
    assert updated.uid == original_uid
    assert updated.title == "new title"
    assert updated.address == "new address"


async def test_handler_dry_run_does_not_persist(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "dryrun")
    token = create_access_token(staff.uid)

    _, body = await _post_bulk(
        db_client,
        token,
        {
            "dry_run": True,
            "rows": [
                {"title": "Ghost 1", "source": "dry", "external_id": "g-1"},
                {"title": "Ghost 2", "source": "dry", "external_id": "g-2"},
                {"title": "Ghost 3", "source": "dry", "external_id": "g-3"},
            ],
        },
    )

    job = await _run_pending_job(db_session, body["job_id"])

    assert job.result == {
        "succeeded": 3,
        "failed": 0,
        "dry_run": True,
        "errors": [],
    }

    spots = (
        await db_session.execute(select(Spot).where(Spot.source == "dry"))
    ).scalars().all()
    assert spots == []


async def test_handler_partial_failure_rolls_back_all(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    staff = await _make_staff(db_session, "partial")
    token = create_access_token(staff.uid)

    original = spots_bulk_module._upsert_spot_row

    async def maybe_failing_upsert(db, row):
        if row.title == "FAIL":
            raise RuntimeError("simulated row failure")
        await original(db, row)

    monkeypatch.setattr(
        spots_bulk_module, "_upsert_spot_row", maybe_failing_upsert
    )

    _, body = await _post_bulk(
        db_client,
        token,
        {
            "rows": [
                {"title": "ok-1", "source": "partial", "external_id": "p-1"},
                {"title": "FAIL", "source": "partial", "external_id": "p-2"},
                {"title": "ok-2", "source": "partial", "external_id": "p-3"},
            ]
        },
    )

    job = await _run_pending_job(db_session, body["job_id"])

    assert job.result["failed"] == 1
    assert job.result["succeeded"] == 0  # 전체 롤백
    assert job.result["dry_run"] is False
    assert job.result["errors"] == [
        {"index": 1, "reason": "simulated row failure"}
    ]

    spots = (
        await db_session.execute(select(Spot).where(Spot.source == "partial"))
    ).scalars().all()
    assert spots == []
