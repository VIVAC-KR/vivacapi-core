from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.models.spot_review import SpotReview
from vivacapi.models.spot_review_report import SpotReviewReport
from vivacapi.models.user import User

# 어드민 목록 정렬 화이트리스트 (임의 컬럼 주입 방지)
_ADMIN_SORTABLE = {"created_at": SpotReviewReport.created_at}
SORTABLE_FIELDS = frozenset(_ADMIN_SORTABLE)


async def create_report(
    session: AsyncSession, *, review_uid: str, reporter_user_uid: str, reason: str
) -> SpotReviewReport:
    existing = await session.execute(
        select(SpotReviewReport).where(
            SpotReviewReport.review_uid == review_uid,
            SpotReviewReport.reporter_user_uid == reporter_user_uid,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AppException(
            ErrorCode.REVIEW_REPORT_ALREADY_EXISTS, "이미 신고한 리뷰입니다"
        )
    report = SpotReviewReport(
        review_uid=review_uid, reporter_user_uid=reporter_user_uid, reason=reason
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def list_reports_admin(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
    sort: str = "created_at",
    order: str = "desc",
    review_uid: str | None = None,
    spot_uid: str | None = None,
) -> tuple[list[tuple[SpotReviewReport, str, str, bool]], int]:
    """(report, reporter_nickname, spot_uid, review_deleted) 리스트와 total."""
    query = (
        select(
            SpotReviewReport, User.nickname, SpotReview.spot_uid, SpotReview.deleted_at
        )
        .join(User, User.uid == SpotReviewReport.reporter_user_uid)
        .join(SpotReview, SpotReview.uid == SpotReviewReport.review_uid)
    )
    if review_uid:
        query = query.where(SpotReviewReport.review_uid == review_uid)
    if spot_uid:
        query = query.where(SpotReview.spot_uid == spot_uid)

    total = await session.scalar(select(func.count()).select_from(query.subquery()))

    column = _ADMIN_SORTABLE.get(sort, SpotReviewReport.created_at)
    ordering = column.desc() if order == "desc" else column.asc()
    result = await session.execute(query.order_by(ordering).offset(offset).limit(limit))
    return [
        (report, nickname, spot_uid, deleted_at is not None)
        for report, nickname, spot_uid, deleted_at in result.all()
    ], total or 0
