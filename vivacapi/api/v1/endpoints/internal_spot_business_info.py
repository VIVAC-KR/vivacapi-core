from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff
from vivacapi.core.limits import enforce_spots_bulk_size
from vivacapi.crud import audit as crud_audit
from vivacapi.models.job import Job, JobType
from vivacapi.schemas.audit import AuditLogEntry
from vivacapi.schemas.spot_business_info import SpotBusinessInfoBulkRequest

router = APIRouter()


@router.get("/{uid}/history", response_model=list[AuditLogEntry])
async def get_spot_business_info_history(
    uid: str,
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogEntry]:
    """spot_business_info 레코드(uid 기준)의 수정 이력을 최신순으로 반환한다."""
    return await crud_audit.get_history(db, "spot_business_info", uid)


@router.post(
    "/bulk",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_spots_bulk_size)],
)
async def enqueue_spot_business_info_bulk_upsert(
    payload: SpotBusinessInfoBulkRequest,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    job = Job(
        type=JobType.SPOT_BUSINESS_INFO_BULK_UPSERT,
        payload=payload.model_dump(mode="json"),
        created_by=staff.uid,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return {"job_id": job.uid}
