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


@router.get(
    "/{uid}/history",
    response_model=list[AuditLogEntry],
    summary="사업자정보 변경 이력 조회",
)
async def get_spot_business_info_history(
    uid: str,
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogEntry]:
    """spot_business_info 레코드(uid 기준)의 변경 이력을 최신순으로 반환한다. 최대 100건까지만 조회되며, 별도 페이지네이션은 지원하지 않는다."""
    return await crud_audit.get_history(db, "spot_business_info", uid)


@router.post(
    "/bulk",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_spots_bulk_size)],
    summary="사업자정보 대량 업서트 등록",
)
async def enqueue_spot_business_info_bulk_upsert(
    payload: SpotBusinessInfoBulkRequest,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """spot_external_id로 spot을 매핑해 사업자정보를 최대 5000건까지 upsert하는 비동기 job을 등록하고 job_id를 즉시 반환한다(처리는 워커가 수행, 완료 여부는 job 조회로 확인). dry_run=true면 저장 없이 유효성만 검증하며, 행 하나라도 spot 매핑에 실패하면 배치 전체가 롤백된다."""
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


@router.get(
    "",
    response_model=list[SpotBusinessInfoAdminListItem],
    summary="사업자정보 목록 조회",
)
async def list_business_info(
    response: Response,
    start: int = Query(0, alias="_start", ge=0),
    end: int = Query(25, alias="_end", ge=0),
    sort: str = Query("uid", alias="_sort"),
    order: str = Query("asc", alias="_order"),
    spot_uid: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[SpotBusinessInfoAdminListItem]:
    """vivac-console용 사업자정보 목록을 페이지네이션(_start/_end)·정렬(_sort/_order)로 조회한다. spot_uid로 필터링할 수 있으며, 화이트리스트에 없는 컬럼으로 정렬을 요청하면 422 VALIDATION_ERROR를 반환한다."""
    # 화이트리스트 밖 정렬 컬럼은 폴백 없이 거부한다 (internal_spots와 동일 정책).
    if sort not in crud_business_info.SORTABLE_FIELDS:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"Not sortable: {sort}")
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


@router.get(
    "/{uid}", response_model=SpotBusinessInfoAdminDetail, summary="사업자정보 단건 조회"
)
async def get_business_info(
    uid: str, db: AsyncSession = Depends(get_db)
) -> SpotBusinessInfoAdminDetail:
    """사업자정보 uid로 단건 상세를 조회한다. spot과 1:1 관계이며, 레코드가 없으면 404 SPOT_BUSINESS_INFO_NOT_FOUND를 반환한다."""
    info = await crud_business_info.get_business_info_by_uid(db, uid)
    if info is None:
        raise AppException(
            ErrorCode.SPOT_BUSINESS_INFO_NOT_FOUND, "Spot business info not found"
        )
    return info


@router.patch(
    "/{uid}", response_model=SpotBusinessInfoAdminDetail, summary="사업자정보 수정"
)
async def update_business_info(
    uid: str,
    payload: SpotBusinessInfoUpdate,
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> SpotBusinessInfoAdminDetail:
    """전달된 필드만 부분 수정하며(exclude_unset), spot_uid 연결은 변경할 수 없다. 수정 이력은 감사 로그(audit log)에 자동 기록되고, 레코드가 없으면 404 SPOT_BUSINESS_INFO_NOT_FOUND를 반환한다."""
    await crud_audit.set_audit_user(db, staff.uid)
    info = await crud_business_info.update_business_info(
        db, uid, payload.model_dump(exclude_unset=True)
    )
    if info is None:
        raise AppException(
            ErrorCode.SPOT_BUSINESS_INFO_NOT_FOUND, "Spot business info not found"
        )
    return info
