import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus, JobType
from app.workers import handlers as handlers_module
from app.workers.job_worker import (
    claim_next_job,
    cleanup_orphaned_jobs,
    process_job,
)
from tests.helpers import make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(db: AsyncSession, suffix: str) -> uuid.UUID:
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    await db.commit()
    return user.uid


async def _make_job(
    db: AsyncSession,
    *,
    created_by: uuid.UUID,
    status: JobStatus = JobStatus.PENDING,
    payload: dict | None = None,
    created_at: datetime | None = None,
) -> Job:
    job = Job(
        type=JobType.SPOTS_BULK_UPSERT,
        status=status,
        payload=payload or {"rows": []},
        created_by=created_by,
    )
    if created_at is not None:
        job.created_at = created_at
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@pytest.fixture(autouse=True)
def _clear_handlers():
    handlers_module.HANDLERS.clear()
    yield
    handlers_module.HANDLERS.clear()


# ---------------------------------------------------------------------------
# cleanup_orphaned_jobs
# ---------------------------------------------------------------------------


async def test_cleanup_orphaned_jobs_flips_running_to_failed(db_session: AsyncSession):
    staff_id = await _make_staff(db_session, "orphan")
    orphan = await _make_job(
        db_session, created_by=staff_id, status=JobStatus.RUNNING
    )
    untouched = await _make_job(
        db_session, created_by=staff_id, status=JobStatus.PENDING
    )

    count = await cleanup_orphaned_jobs(db_session)

    await db_session.refresh(orphan)
    await db_session.refresh(untouched)
    assert count == 1
    assert orphan.status == JobStatus.FAILED
    assert orphan.error == "orphaned"
    assert orphan.finished_at is not None
    assert untouched.status == JobStatus.PENDING


async def test_cleanup_orphaned_jobs_returns_zero_when_nothing_running(
    db_session: AsyncSession,
):
    staff_id = await _make_staff(db_session, "noorphan")
    await _make_job(db_session, created_by=staff_id, status=JobStatus.PENDING)

    count = await cleanup_orphaned_jobs(db_session)

    assert count == 0


# ---------------------------------------------------------------------------
# claim_next_job
# ---------------------------------------------------------------------------


async def test_claim_next_job_picks_oldest_pending(db_session: AsyncSession):
    staff_id = await _make_staff(db_session, "claim")
    now = datetime.now(timezone.utc)
    newer = await _make_job(
        db_session, created_by=staff_id, created_at=now
    )
    older = await _make_job(
        db_session, created_by=staff_id, created_at=now - timedelta(minutes=5)
    )

    claimed = await claim_next_job(db_session)

    assert claimed is not None
    assert claimed.uid == older.uid
    assert claimed.status == JobStatus.RUNNING
    assert claimed.started_at is not None
    # 두 번째 job은 그대로 PENDING
    await db_session.refresh(newer)
    assert newer.status == JobStatus.PENDING


async def test_claim_next_job_returns_none_when_no_pending(db_session: AsyncSession):
    staff_id = await _make_staff(db_session, "nopending")
    await _make_job(db_session, created_by=staff_id, status=JobStatus.SUCCEEDED)

    claimed = await claim_next_job(db_session)

    assert claimed is None


# ---------------------------------------------------------------------------
# process_job
# ---------------------------------------------------------------------------


async def test_process_job_runs_handler_and_records_result(db_session: AsyncSession):
    staff_id = await _make_staff(db_session, "process")
    job = await _make_job(
        db_session,
        created_by=staff_id,
        status=JobStatus.RUNNING,
        payload={"rows": [1, 2, 3]},
    )

    async def fake_handler(_db, payload):
        return {"succeeded": len(payload["rows"]), "failed": 0}

    handlers_module.HANDLERS[JobType.SPOTS_BULK_UPSERT] = fake_handler

    await process_job(db_session, job)

    await db_session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED
    assert job.result == {"succeeded": 3, "failed": 0}
    assert job.error is None
    assert job.finished_at is not None


async def test_process_job_records_traceback_on_handler_exception(
    db_session: AsyncSession,
):
    staff_id = await _make_staff(db_session, "fail")
    job = await _make_job(
        db_session, created_by=staff_id, status=JobStatus.RUNNING
    )

    async def boom_handler(_db, _payload):
        raise RuntimeError("boom")

    handlers_module.HANDLERS[JobType.SPOTS_BULK_UPSERT] = boom_handler

    await process_job(db_session, job)

    await db_session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert "RuntimeError" in job.error
    assert "boom" in job.error
    assert job.finished_at is not None


async def test_process_job_marks_failed_when_no_handler(db_session: AsyncSession):
    staff_id = await _make_staff(db_session, "nohandler")
    job = await _make_job(
        db_session, created_by=staff_id, status=JobStatus.RUNNING
    )
    # HANDLERS는 _clear_handlers 픽스처로 비어있음

    await process_job(db_session, job)

    await db_session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert "No handler" in job.error
    assert job.finished_at is not None


# ---------------------------------------------------------------------------
# 통합: 1사이클 (claim + process)
# ---------------------------------------------------------------------------


async def test_full_cycle_processes_pending_job(db_session: AsyncSession):
    staff_id = await _make_staff(db_session, "cycle")
    job = await _make_job(
        db_session, created_by=staff_id, payload={"x": 42}
    )

    captured: list = []

    async def fake_handler(_db, payload):
        captured.append(payload)
        return {"echo": payload["x"]}

    handlers_module.HANDLERS[JobType.SPOTS_BULK_UPSERT] = fake_handler

    claimed = await claim_next_job(db_session)
    assert claimed is not None
    await process_job(db_session, claimed)

    await db_session.refresh(job)
    assert captured == [{"x": 42}]
    assert job.status == JobStatus.SUCCEEDED
    assert job.result == {"echo": 42}
