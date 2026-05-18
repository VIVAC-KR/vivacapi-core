import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AppException, ErrorCode
from app.crud.job import get_job_by_id
from app.schemas.job import JobRead

router = APIRouter()


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobRead:
    job = await get_job_by_id(db, job_id)
    if job is None:
        raise AppException(ErrorCode.JOB_NOT_FOUND, "Job not found")
    return JobRead.model_validate(job)
