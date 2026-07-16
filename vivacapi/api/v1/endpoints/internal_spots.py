from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff, require_role
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.limits import enforce_spots_bulk_size
from vivacapi.crud import audit as crud_audit
from vivacapi.crud import spot as crud_spot
from vivacapi.crud.user import get_user_by_id
from vivacapi.models.job import Job, JobType
from vivacapi.models.spot import PipelineStatus
from vivacapi.models.user import StaffRole
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


@router.get(
    "/{uid}/history", response_model=list[AuditLogEntry], summary="스팟 변경 이력 조회"
)
async def get_spot_history(
    uid: str,
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogEntry]:
    """spot 레코드의 수정 이력을 최신순으로 반환한다."""
    return await crud_audit.get_history(db, "spots", uid)


@router.post(
    "/bulk",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(enforce_spots_bulk_size),
        Depends(require_role(StaffRole.SUPERUSER)),
    ],
    summary="스팟 대량 upsert 작업 큐잉",
)
async def enqueue_spots_bulk_upsert(
    payload: SpotBulkRequest,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """spot 대량 upsert를 비동기 Job으로 큐잉한다 (SUPERUSER 전용).

    즉시 처리하지 않고 job_id만 반환한다 — 실제 upsert는 워커가 처리한다.
    rows는 최대 5000건, 요청 바디는 5 MiB를 넘으면 거부된다. dry_run=True면
    워커가 검증만 수행하고 실제 반영은 하지 않는다.
    """
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


@router.get("", response_model=list[SpotAdminListItem], summary="스팟 어드민 목록 조회")
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
    include_deleted: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> list[SpotAdminListItem]:
    """vivac-console용 spot 목록 (Refine simple-rest 규약, X-Total-Count 헤더 포함).

    sort는 SORTABLE_FIELDS 화이트리스트 밖이면 400으로 거부한다(폴백 없음).
    region_province/source/pipeline_status/assigned_to_uid는 정확일치 필터로 AND 결합된다.
    include_deleted=False(기본)면 소프트 삭제된 spot은 목록에서 제외된다.
    """
    # distinct/{field}와 동일하게 화이트리스트 밖 정렬 컬럼은 폴백 없이 거부한다.
    if sort not in crud_spot.SORTABLE_FIELDS:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"Not sortable: {sort}")
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
        include_deleted=include_deleted,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/stats", response_model=SpotStats, summary="스팟 대시보드 통계 조회")
async def spot_stats(
    staff: CurrentStaff, db: AsyncSession = Depends(get_db)
) -> SpotStats:
    """대시보드 통계 (총계·소스별·지역별·My Queue 등)."""
    return SpotStats(**await crud_spot.get_spot_stats(db, staff_uid=staff.uid))


@router.post(
    "/assignments",
    response_model=SpotAssignmentResponse,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="검증 대기 스팟 할당",
)
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


@router.get(
    "/distinct/{field}", response_model=list[str], summary="필터 옵션 distinct 값 조회"
)
async def distinct_values(field: str, db: AsyncSession = Depends(get_db)) -> list[str]:
    """필터 드롭다운 옵션 — 화이트리스트 필드의 distinct 값."""
    if field not in crud_spot.FILTERABLE_FIELDS:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"Not filterable: {field}")
    return await crud_spot.list_distinct(db, field)


@router.get("/{uid}", response_model=SpotAdminDetail, summary="스팟 어드민 상세 조회")
async def get_spot(uid: str, db: AsyncSession = Depends(get_db)) -> SpotAdminDetail:
    """spot 단건을 편집 폼용으로 전체 컬럼 조회한다.

    공개 API와 달리 pipeline_status/삭제 여부와 무관하게 조회 가능하다
    (소프트 삭제된 spot도 복구 화면에서 보여야 하므로).
    """
    spot = await crud_spot.get_spot_by_uid(db, uid)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    return spot


@router.patch("/{uid}", response_model=SpotAdminDetail, summary="스팟 정보 수정")
async def update_spot(
    uid: str,
    payload: SpotUpdate,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> SpotAdminDetail:
    """전달된 필드만 부분 수정한다(exclude_unset).

    spot이 ENRICHED 상태(검증 대기)인 경우 본인에게 할당된 항목만 수정할 수
    있다 — 타 staff에게 할당되었거나 미할당 상태면 FORBIDDEN. pipeline_status를
    바꾸는 요청은 ALLOWED_PIPELINE_TRANSITIONS 화이트리스트에 없는 전이면 거부된다.
    수정 이력은 자동으로 감사 로그에 남는다(GET /{uid}/history로 조회).
    """
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


@router.delete(
    "/{uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="스팟 소프트 삭제",
)
async def delete_spot(
    uid: str,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> None:
    """soft delete. deleted_at만 세팅 — 복구는 POST /{uid}/restore."""
    spot = await crud_spot.get_spot_by_uid(db, uid)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    await crud_audit.set_audit_user(db, staff.uid)
    await crud_spot.delete_spot(db, spot)


@router.post(
    "/{uid}/restore",
    response_model=SpotAdminDetail,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="소프트 삭제된 스팟 복구",
)
async def restore_spot(
    uid: str,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> SpotAdminDetail:
    """deleted_at을 해제해 소프트 삭제 이전 상태로 되돌린다(MANAGER 이상)."""
    spot = await crud_spot.get_spot_by_uid(db, uid)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    await crud_audit.set_audit_user(db, staff.uid)
    return await crud_spot.restore_spot(db, spot)
