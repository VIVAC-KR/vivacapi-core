from datetime import datetime

from pydantic import BaseModel, Field


class SpotReviewReportCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


# ---------------------------------------------------------------------------
# Internal admin (vivac-console) — 신고 큐 조회
# ---------------------------------------------------------------------------


class SpotReviewReportAdminOut(BaseModel):
    uid: str
    review_uid: str
    spot_uid: str
    reporter_user_uid: str
    reporter_nickname: str
    reason: str
    review_deleted: bool
    created_at: datetime | None
