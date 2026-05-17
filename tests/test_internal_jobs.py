import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.job import Job, JobStatus, JobType
from tests.helpers import bearer, make_user


# ---------------------------------------------------------------------------
# GET /internal/jobs/{job_id}
# ---------------------------------------------------------------------------


async def _create_job(
    db: AsyncSession,
    *,
    created_by: uuid.UUID,
    status: JobStatus = JobStatus.SUCCEEDED,
    result: dict | None = None,
    error: str | None = None,
) -> Job:
    job = Job(
        type=JobType.SPOTS_BULK_UPSERT,
        status=status,
        payload={"rows": []},
        result=result,
        error=error,
        created_by=created_by,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def test_staff_can_read_existing_job(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await make_user(db_session, email="staff@example.com", google_sub="sub-staff")
    staff.is_staff = True
    await db_session.commit()

    job = await _create_job(
        db_session,
        created_by=staff.uid,
        result={"succeeded": 3, "failed": 0},
    )

    token = create_access_token(str(staff.uid))
    response = await db_client.get(
        f"/internal/jobs/{job.uid}", headers=bearer(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == str(job.uid)
    assert body["type"] == "spots_bulk_upsert"
    assert body["status"] == "succeeded"
    assert body["result"] == {"succeeded": 3, "failed": 0}
    assert body["error"] is None


async def test_nonexistent_job_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await make_user(db_session, email="staff2@example.com", google_sub="sub-staff2")
    staff.is_staff = True
    await db_session.commit()

    token = create_access_token(str(staff.uid))
    response = await db_client.get(
        f"/internal/jobs/{uuid.uuid4()}", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_non_staff_user_gets_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    user = await make_user(db_session, email="user@example.com", google_sub="sub-user")
    # is_staff 기본값 False

    token = create_access_token(str(user.uid))
    response = await db_client.get(
        f"/internal/jobs/{uuid.uuid4()}", headers=bearer(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_unauthenticated_gets_401(db_client: AsyncClient):
    response = await db_client.get(f"/internal/jobs/{uuid.uuid4()}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
