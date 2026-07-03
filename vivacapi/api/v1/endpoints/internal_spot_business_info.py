from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.limits import enforce_spots_bulk_size
from vivacapi.crud import audit as crud_audit
from vivacapi.crud import spot_business_info as crud_business_info
from vivacapi.models.job import Job, JobType
from vivacapi.schemas.audit import AuditLogEntry
from vivacapi.schemas.spot_business_info import (
    SpotBusinessInfoAdminDetail,
    SpotBusinessInfoAdminListItem,
    SpotBusinessInfoBulkRequest,
    SpotBusinessInfoUpdate,
)

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


# ---------------------------------------------------------------------------
# 단건 조회/수정 (vivac-console) — Refine simple-rest 호환
# ---------------------------------------------------------------------------


@router.get("", response_model=list[SpotBusinessInfoAdminListItem])
async def list_business_info(
    response: Response,
    start: int = Query(0, alias="_start", ge=0),
    end: int = Query(25, alias="_end", ge=0),
    sort: str = Query("uid", alias="_sort"),
    order: str = Query("asc", alias="_order"),
    spot_uid: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[SpotBusinessInfoAdminListItem]:
    items, total = await crud_business_info.list_business_info_admin(
        db,
        offset=start,
        limit=max(end - start, 0),
        sort=sort,
        order=order.lower(),
        spot_uid=spot_uid,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/{uid}", response_model=SpotBusinessInfoAdminDetail)
async def get_business_info(
    uid: str, db: AsyncSession = Depends(get_db)
) -> SpotBusinessInfoAdminDetail:
    info = await crud_business_info.get_business_info_by_uid(db, uid)
    if info is None:
        raise AppException(
            ErrorCode.SPOT_BUSINESS_INFO_NOT_FOUND, "Spot business info not found"
        )
    return info


@router.patch("/{uid}", response_model=SpotBusinessInfoAdminDetail)
async def update_business_info(
    uid: str,
    payload: SpotBusinessInfoUpdate,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> SpotBusinessInfoAdminDetail:
    await crud_audit.set_audit_user(db, staff.uid)
    info = await crud_business_info.update_business_info(
        db, uid, payload.model_dump(exclude_unset=True)
    )
    if info is None:
        raise AppException(
            ErrorCode.SPOT_BUSINESS_INFO_NOT_FOUND, "Spot business info not found"
        )
    return info
