from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.security import create_access_token
from vivacapi.models.job import Job, JobStatus, JobType
from vivacapi.models.user import StaffRole
from vivacapi.workers import db_dump as db_dump_module
from vivacapi.workers.db_dump import db_dump_handler
from tests.helpers import bearer, make_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(
    db: AsyncSession, suffix: str, role: StaffRole = StaffRole.SUPERUSER
):
    """DB 덤프는 SUPERUSER 전용이라 이 파일의 기본 staff는 SUPERUSER로 만든다."""
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user


async def _make_succeeded_job(db: AsyncSession, staff_uid: str, result: dict) -> Job:
    job = Job(
        type=JobType.DB_DUMP,
        payload={},
        created_by=staff_uid,
        status=JobStatus.SUCCEEDED,
        result=result,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# POST /v1/internal/db-dumps — auth / enqueue
# ---------------------------------------------------------------------------


async def test_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.post("/v1/internal/db-dumps")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_non_staff_returns_403(db_client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session, email="user@example.com", google_sub="sub-user")
    token = create_access_token(user.uid)

    response = await db_client.post("/v1/internal/db-dumps", headers=bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_manager_role_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    """db-dumps는 SUPERUSER 전용 — MANAGER는 staff지만 거부된다."""
    manager = await _make_staff(db_session, "manager-dump", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)

    response = await db_client.post("/v1/internal/db-dumps", headers=bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_superuser_enqueue_returns_202_with_job_id(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "enqueue")
    token = create_access_token(staff.uid)

    response = await db_client.post("/v1/internal/db-dumps", headers=bearer(token))

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert isinstance(job_id, str) and job_id

    job = (await db_session.execute(select(Job).where(Job.uid == job_id))).scalar_one()
    assert job.type == JobType.DB_DUMP
    assert job.status == JobStatus.PENDING
    assert job.created_by == staff.uid


# ---------------------------------------------------------------------------
# GET /v1/internal/db-dumps/{job_id}/download
# ---------------------------------------------------------------------------


async def test_download_unknown_job_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "dl-404")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/db-dumps/does-not-exist/download", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_download_not_ready_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "dl-409")
    token = create_access_token(staff.uid)

    job = Job(type=JobType.DB_DUMP, payload={}, created_by=staff.uid)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    response = await db_client.get(
        f"/v1/internal/db-dumps/{job.uid}/download", headers=bearer(token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DB_DUMP_NOT_READY"


async def test_download_succeeded_job_returns_presigned_url(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    staff = await _make_staff(db_session, "dl-ok")
    token = create_access_token(staff.uid)

    job = await _make_succeeded_job(
        db_session,
        staff.uid,
        {"s3_key": "db-dumps/abc123.dump", "size_bytes": 42, "format": "pg_dump-custom"},
    )

    monkeypatch.setattr(
        storage,
        "generate_presigned_get",
        lambda key, filename=None: f"https://s3.fake/{key}?filename={filename}",
    )

    response = await db_client.get(
        f"/v1/internal/db-dumps/{job.uid}/download", headers=bearer(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["download_url"] == (
        f"https://s3.fake/db-dumps/abc123.dump?filename=vivac-db-dump-{job.uid}.dump"
    )
    assert body["expires_in"] > 0


async def test_download_manager_role_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "dl-manager", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)

    job = await _make_succeeded_job(
        db_session,
        manager.uid,
        {"s3_key": "db-dumps/abc.dump", "size_bytes": 1, "format": "pg_dump-custom"},
    )

    response = await db_client.get(
        f"/v1/internal/db-dumps/{job.uid}/download", headers=bearer(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Worker handler — 실제 pg_dump 실행, S3 업로드만 모킹
# ---------------------------------------------------------------------------


async def test_handler_produces_valid_dump_and_uploads(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    uploaded: list[tuple[str, str]] = []

    async def fake_upload_file(key: str, file_path: str) -> None:
        content = Path(file_path).read_bytes()
        # pg_dump custom format(-Fc) 파일은 "PGDMP" 매직 바이트로 시작한다.
        assert content.startswith(b"PGDMP")
        uploaded.append((key, file_path))

    monkeypatch.setattr(db_dump_module, "upload_file", fake_upload_file)

    result = await db_dump_handler(db_session, {})

    assert result["format"] == "pg_dump-custom"
    assert result["size_bytes"] > 0
    assert result["s3_key"].startswith("db-dumps/")
    assert result["s3_key"].endswith(".dump")
    assert len(uploaded) == 1
    assert uploaded[0][0] == result["s3_key"]
