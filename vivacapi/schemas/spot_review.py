from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpotReviewCreate(BaseModel):
    rating: int = Field(ge=0, le=10)
    content: str | None = Field(None, max_length=2000)


class SpotReviewUpdate(BaseModel):
    """부분 수정. 전달된 필드만 반영(exclude_unset)."""

    rating: int | None = Field(None, ge=0, le=10)
    content: str | None = Field(None, max_length=2000)


class SpotReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    spot_uid: str
    user_uid: str
    nickname: str
    rating: int
    content: str | None
    created_at: datetime | None
    updated_at: datetime | None
