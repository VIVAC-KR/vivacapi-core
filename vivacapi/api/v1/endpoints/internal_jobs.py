from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud.job import get_job_by_id
from vivacapi.schemas.job import JobRead

router = APIRouter()


@router.get("/{job_id}", response_model=JobRead, summary="job 상태 조회")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobRead:
    """spot bulk upsert 등 비동기로 큐잉된 작업의 처리 상태를 조회한다. job은
    엔드포인트가 요청을 즉시 202로 접수하며 만들어지고, 워커가 이후 백그라운드로
    처리한다 (status: pending → running → succeeded/failed). 완료 시 result에
    처리 결과가, 실패 시 error에 사유가 담긴다."""
    job = await get_job_by_id(db, job_id)
    if job is None:
        raise AppException(ErrorCode.JOB_NOT_FOUND, "Job not found")
    return JobRead.model_validate(job)
