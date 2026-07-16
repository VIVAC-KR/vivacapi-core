from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpotReviewCreate(BaseModel):
    """리뷰 작성 요청. rating은 0~10(0.5점 단위, 10=별 5개)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rating": 9,
                "content": "사이트가 넓고 평평해서 텐트 치기 좋았어요. 화장실도 깨끗해요.",
            }
        }
    )

    rating: int = Field(ge=0, le=10)
    content: str | None = Field(None, max_length=2000)


class SpotReviewUpdate(BaseModel):
    """부분 수정. 전달된 필드만 반영(exclude_unset)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rating": 8,
                "content": "재방문했는데 자리가 좁아져서 살짝 아쉬웠어요",
            }
        }
    )

    rating: int | None = Field(None, ge=0, le=10)
    content: str | None = Field(None, max_length=2000)


class SpotReviewOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "8bYkV3nQmZxP2wRj9sTfC7",
                "spot_uid": "6dHkQ2mNpXyB4jRt8wLsA1",
                "user_uid": "3fPqR7mNxWyT9jKs2vLbD5",
                "nickname": "불멍러",
                "rating": 9,
                "content": "사이트가 넓고 평평해서 텐트 치기 좋았어요. 화장실도 깨끗해요.",
                "created_at": "2026-07-10T09:30:00+09:00",
                "updated_at": "2026-07-10T09:30:00+09:00",
            }
        },
    )

    uid: str
    spot_uid: str
    user_uid: str
    nickname: str
    rating: int
    content: str | None
    created_at: datetime | None
    updated_at: datetime | None
