from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.api.v1.endpoints.summaries import (
    ENQUEUE_DB_DUMP_SUMMARY,
    GET_DB_DUMP_DOWNLOAD_URL_SUMMARY,
)
from vivacapi.core import storage
from vivacapi.core.config import settings
from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff, require_role
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud.job import get_job_by_id
from vivacapi.models.job import Job, JobStatus, JobType
from vivacapi.models.user import StaffRole
from vivacapi.schemas.job import DbDumpDownload

router = APIRouter()


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_role(StaffRole.SUPERUSER))],
    summary=ENQUEUE_DB_DUMP_SUMMARY,
)
async def enqueue_db_dump(
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """전체 DB를 pg_dump(custom format)로 덤프하는 작업을 큐잉한다 (SUPERUSER 전용).

    즉시 처리하지 않고 job_id만 반환한다 — 실제 덤프는 워커가 처리한다.
    상태는 GET /v1/internal/jobs/{job_id}로 폴링한다.
    """
    job = Job(type=JobType.DB_DUMP, payload={}, created_by=staff.uid)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return {"job_id": job.uid}


@router.get(
    "/{job_id}/download",
    response_model=DbDumpDownload,
    dependencies=[Depends(require_role(StaffRole.SUPERUSER))],
    summary=GET_DB_DUMP_DOWNLOAD_URL_SUMMARY,
)
async def get_db_dump_download_url(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> DbDumpDownload:
    """성공한 db_dump job의 결과물을 내려받을 presigned S3 URL을 발급한다."""
    job = await get_job_by_id(db, job_id)
    if job is None or job.type != JobType.DB_DUMP:
        raise AppException(ErrorCode.JOB_NOT_FOUND, "Job not found")
    if job.status != JobStatus.SUCCEEDED:
        raise AppException(
            ErrorCode.DB_DUMP_NOT_READY, "Dump job has not succeeded yet"
        )

    url = storage.generate_presigned_get(
        job.result["s3_key"], filename=f"vivac-db-dump-{job_id}.dump"
    )
    return DbDumpDownload(
        download_url=url, expires_in=settings.S3_PRESIGN_EXPIRE_SECONDS
    )
