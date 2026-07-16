from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import get_current_user
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_review as crud_review
from vivacapi.crud import spot_review_report as crud_report
from vivacapi.models.spot import Spot
from vivacapi.models.spot_review import SpotReview
from vivacapi.models.user import StaffRole, User
from vivacapi.schemas.spot_review import (
    SpotReviewCreate,
    SpotReviewOut,
    SpotReviewUpdate,
)
from vivacapi.schemas.spot_review_report import SpotReviewReportCreate

router = APIRouter()

# 등급 간 순서 비교용 (core/deps.py의 _STAFF_ROLE_RANK와 동일한 이유).
_STAFF_ROLE_RANK = {
    StaffRole.STAFF: 1,
    StaffRole.MANAGER: 2,
    StaffRole.SUPERUSER: 3,
}


async def _get_spot_or_404(
    spot_uid: str, session: AsyncSession = Depends(get_db)
) -> Spot:
    spot = await crud_spot.get_spot_by_uid(session, spot_uid, published_only=True)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    return spot


async def _get_active_review_or_404(
    review_uid: str,
    spot: Spot = Depends(_get_spot_or_404),
    session: AsyncSession = Depends(get_db),
) -> SpotReview:
    review = await crud_review.get_review_by_uid(session, review_uid)
    if review is None or review.spot_uid != spot.uid or review.deleted_at is not None:
        raise AppException(ErrorCode.REVIEW_NOT_FOUND, "Review not found")
    return review


def _is_moderator(user: User) -> bool:
    return (
        user.is_staff
        and _STAFF_ROLE_RANK[user.staff_role] >= _STAFF_ROLE_RANK[StaffRole.MANAGER]
    )


def _to_out(review: SpotReview, nickname: str) -> SpotReviewOut:
    return SpotReviewOut(
        uid=review.uid,
        spot_uid=review.spot_uid,
        user_uid=review.user_id,
        nickname=nickname,
        rating=review.rating,
        content=review.content,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.post(
    "/spots/{spot_uid}/reviews",
    response_model=SpotReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="리뷰 작성",
)
async def create_review(
    payload: SpotReviewCreate,
    spot: Spot = Depends(_get_spot_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SpotReviewOut:
    """spot당 유저 1명은 활성 리뷰를 하나만 가질 수 있다(이미 있으면 409
    REVIEW_ALREADY_EXISTS, 소프트 삭제 후에는 재작성 가능). 작성 즉시
    spot의 rating_avg/review_count가 재계산된다."""
    review = await crud_review.create_review(
        session,
        spot_uid=spot.uid,
        user_uid=user.uid,
        rating=payload.rating,
        content=payload.content,
    )
    return _to_out(review, user.nickname)


@router.get(
    "/spots/{spot_uid}/reviews",
    response_model=list[SpotReviewOut],
    summary="리뷰 목록 조회",
)
async def list_reviews(
    spot: Spot = Depends(_get_spot_or_404),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[SpotReviewOut]:
    """소프트 삭제된 리뷰는 제외하고 최신순으로 반환한다."""
    rows, _total = await crud_review.list_reviews_by_spot(
        session, spot.uid, offset=offset, limit=limit
    )
    return [_to_out(review, nickname) for review, nickname in rows]


@router.patch(
    "/spots/{spot_uid}/reviews/{review_uid}",
    response_model=SpotReviewOut,
    summary="리뷰 수정",
)
async def update_review(
    payload: SpotReviewUpdate,
    review: SpotReview = Depends(_get_active_review_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SpotReviewOut:
    """부분 수정. 본인 리뷰만 수정 가능(타인 리뷰면 403 FORBIDDEN). rating을
    바꾸면 spot의 rating_avg가 재계산된다."""
    if review.user_id != user.uid:
        raise AppException(ErrorCode.FORBIDDEN, "본인 리뷰만 수정할 수 있습니다")
    review = await crud_review.update_review(
        session, review, payload.model_dump(exclude_unset=True)
    )
    return _to_out(review, user.nickname)


@router.delete(
    "/spots/{spot_uid}/reviews/{review_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="리뷰 삭제",
)
async def delete_review(
    review: SpotReview = Depends(_get_active_review_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """소프트 삭제. 본인 리뷰이거나, MANAGER 이상 staff는 신고된 리뷰
    조치 목적으로 타인 리뷰도 삭제할 수 있다(그 외는 403 FORBIDDEN).
    삭제 후 spot의 rating_avg/review_count가 재계산된다."""
    if review.user_id != user.uid and not _is_moderator(user):
        raise AppException(ErrorCode.FORBIDDEN, "본인 리뷰만 삭제할 수 있습니다")
    await crud_review.soft_delete_review(session, review)


@router.post(
    "/spots/{spot_uid}/reviews/{review_uid}/reports",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="리뷰 신고 접수",
)
async def report_review(
    payload: SpotReviewReportCreate,
    review: SpotReview = Depends(_get_active_review_or_404),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """본인 리뷰는 신고할 수 없고, 같은 유저가 같은 리뷰를 중복 신고하면
    409 REVIEW_REPORT_ALREADY_EXISTS다. 신고는 콘솔의 신고 목록에 쌓일 뿐
    리뷰를 자동으로 숨기지 않으며, staff가 검토 후 직접 삭제해야 한다."""
    if review.user_id == user.uid:
        raise AppException(ErrorCode.FORBIDDEN, "본인 리뷰는 신고할 수 없습니다")
    await crud_report.create_report(
        session,
        review_uid=review.uid,
        reporter_user_uid=user.uid,
        reason=payload.reason,
    )
