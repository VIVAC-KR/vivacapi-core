from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.limits import enforce_spots_bulk_size
from vivacapi.crud import spot as crud_spot
from vivacapi.models.job import Job, JobType
from vivacapi.schemas.spot import (
    SpotAdminDetail,
    SpotAdminListItem,
    SpotBulkRequest,
    SpotUpdate,
)

router = APIRouter()


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
    db: AsyncSession = Depends(get_db),
) -> list[SpotAdminListItem]:
    items, total = await crud_spot.list_spots_admin(
        db,
        offset=start,
        limit=max(end - start, 0),
        sort=sort,
        order=order.lower(),
        title=title_like,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


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
    db: AsyncSession = Depends(get_db),
) -> SpotAdminDetail:
    spot = await crud_spot.update_spot(
        db, uid, payload.model_dump(exclude_unset=True)
    )
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    return spot
