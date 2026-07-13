from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.limits import enforce_spots_bulk_size
from vivacapi.crud import audit as crud_audit
from vivacapi.crud import spot as crud_spot
from vivacapi.crud.user import get_user_by_id
from vivacapi.models.job import Job, JobType
from vivacapi.models.spot import PipelineStatus
from vivacapi.schemas.audit import AuditLogEntry
from vivacapi.schemas.spot import (
    SpotAdminDetail,
    SpotAdminListItem,
    SpotAssignmentRequest,
    SpotAssignmentResponse,
    SpotBulkRequest,
    SpotStats,
    SpotUpdate,
)

router = APIRouter()


@router.get("/{uid}/history", response_model=list[AuditLogEntry])
async def get_spot_history(
    uid: str,
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogEntry]:
    """spot 레코드의 수정 이력을 최신순으로 반환한다."""
    return await crud_audit.get_history(db, "spots", uid)


@router.post(
    "/bulk",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_spots_bulk_size)],
)
async def enqueue_spots_bulk_upsert(
    payload: SpotBulkRequest,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    job = Job(
        type=JobType.SPOTS_BULK_UPSERT,
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


@router.get("", response_model=list[SpotAdminListItem])
async def list_spots(
    response: Response,
    start: int = Query(0, alias="_start", ge=0),
    end: int = Query(25, alias="_end", ge=0),
    sort: str = Query("uid", alias="_sort"),
    order: str = Query("asc", alias="_order"),
    title_like: str | None = Query(None),
    region_province: str | None = Query(None),
    source: str | None = Query(None),
    pipeline_status: str | None = Query(None),
    assigned_to_uid: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[SpotAdminListItem]:
    items, total = await crud_spot.list_spots_admin(
        db,
        offset=start,
        limit=max(end - start, 0),
        sort=sort,
        order=order.lower(),
        title=title_like,
        filters={
            "region_province": region_province,
            "source": source,
            "pipeline_status": pipeline_status,
            "assigned_to_uid": assigned_to_uid,
        },
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/stats", response_model=SpotStats)
async def spot_stats(
    staff: CurrentStaff, db: AsyncSession = Depends(get_db)
) -> SpotStats:
    """대시보드 통계 (총계·소스별·지역별·My Queue 등)."""
    return SpotStats(**await crud_spot.get_spot_stats(db, staff_uid=staff.uid))


@router.post("/assignments", response_model=SpotAssignmentResponse)
async def assign_spots(
    payload: SpotAssignmentRequest,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> SpotAssignmentResponse:
    """검증 대기(ENRICHED) 중 미할당 spot을 지정한 staff uid에게 누적 할당한다."""
    target = await get_user_by_id(db, payload.user_uid)
    if target is None or not target.is_staff:
        raise AppException(ErrorCode.USER_NOT_FOUND, "Staff user not found")

    assigned_count = await crud_spot.assign_spots(
        db, user_uid=payload.user_uid, count=payload.count
    )
    return SpotAssignmentResponse(assigned_count=assigned_count)


@router.get("/distinct/{field}", response_model=list[str])
async def distinct_values(
    field: str, db: AsyncSession = Depends(get_db)
) -> list[str]:
    """필터 드롭다운 옵션 — 화이트리스트 필드의 distinct 값."""
    if field not in crud_spot.FILTERABLE_FIELDS:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"Not filterable: {field}")
    return await crud_spot.list_distinct(db, field)


@router.get("/{uid}", response_model=SpotAdminDetail)
async def get_spot(uid: str, db: AsyncSession = Depends(get_db)) -> SpotAdminDetail:
    spot = await crud_spot.get_spot_by_uid(db, uid)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    return spot


@router.patch("/{uid}", response_model=SpotAdminDetail)
async def update_spot(
    uid: str,
    payload: SpotUpdate,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> SpotAdminDetail:
    data = payload.model_dump(exclude_unset=True)

    current = await crud_spot.get_spot_by_uid(db, uid)
    if current is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")

    if current.pipeline_status == PipelineStatus.ENRICHED and (
        current.assigned_to_uid is None or current.assigned_to_uid != staff.uid
    ):
        raise AppException(
            ErrorCode.FORBIDDEN, "본인에게 할당된 검증 대기 항목만 수정할 수 있습니다."
        )

    if "pipeline_status" in data:
        transition = (current.pipeline_status, data["pipeline_status"])
        if transition not in crud_spot.ALLOWED_PIPELINE_TRANSITIONS:
            raise AppException(
                ErrorCode.VALIDATION_ERROR,
                f"허용되지 않는 상태 전이입니다: {current.pipeline_status} -> "
                f"{data['pipeline_status']}",
            )

    await crud_audit.set_audit_user(db, staff.uid)
    spot = await crud_spot.update_spot(db, uid, data)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    return spot
