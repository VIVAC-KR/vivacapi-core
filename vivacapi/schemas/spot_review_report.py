from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpotReviewReportCreate(BaseModel):
    """리뷰 신고 접수 요청. reason은 자유 텍스트."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"reason": "광고성 도배 댓글로 보입니다"}}
    )

    reason: str = Field(min_length=1, max_length=1000)


# ---------------------------------------------------------------------------
# Internal admin (vivac-console) — 신고 큐 조회
# ---------------------------------------------------------------------------


class SpotReviewReportAdminOut(BaseModel):
    """콘솔용 신고 상세. review_deleted가 true면 이미 리뷰가 삭제되어
    조치가 끝난 신고, false면 아직 검토 대기 중인 신고다."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uid": "5tRnQ8mXpZyK3jWs7vLbF2",
                "review_uid": "8bYkV3nQmZxP2wRj9sTfC7",
                "spot_uid": "6dHkQ2mNpXyB4jRt8wLsA1",
                "reporter_user_uid": "9jKs2vLbD5fPqR7mNxWyT3",
                "reporter_nickname": "익명의행인",
                "reason": "광고성 도배 댓글로 보입니다",
                "review_deleted": False,
                "created_at": "2026-07-12T14:05:00+09:00",
            }
        }
    )

    uid: str
    review_uid: str
    spot_uid: str
    reporter_user_uid: str
    reporter_nickname: str
    reason: str
    review_deleted: bool
    created_at: datetime | None
