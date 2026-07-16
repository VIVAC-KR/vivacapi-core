from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot_review_report as crud_report
from vivacapi.schemas.spot_review_report import SpotReviewReportAdminOut

router = APIRouter()


@router.get("", response_model=list[SpotReviewReportAdminOut])
async def list_review_reports(
    response: Response,
    start: int = Query(0, alias="_start", ge=0),
    end: int = Query(25, alias="_end", ge=0),
    sort: str = Query("created_at", alias="_sort"),
    order: str = Query("desc", alias="_order"),
    review_uid: str | None = Query(None),
    spot_uid: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[SpotReviewReportAdminOut]:
    if sort not in crud_report.SORTABLE_FIELDS:
        raise AppException(ErrorCode.VALIDATION_ERROR, f"Not sortable: {sort}")
    items, total = await crud_report.list_reports_admin(
        db,
        offset=start,
        limit=max(end - start, 0),
        sort=sort,
        order=order.lower(),
        review_uid=review_uid,
        spot_uid=spot_uid,
    )
    response.headers["X-Total-Count"] = str(total)
    return [
        SpotReviewReportAdminOut(
            uid=report.uid,
            review_uid=report.review_uid,
            spot_uid=spot_uid,
            reporter_user_uid=report.reporter_user_uid,
            reporter_nickname=nickname,
            reason=report.reason,
            review_deleted=review_deleted,
            created_at=report.created_at,
        )
        for report, nickname, spot_uid, review_deleted in items
    ]
