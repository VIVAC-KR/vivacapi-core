from pydantic import BaseModel, ConfigDict, Field, field_validator

from vivacapi.models.spot_image import SpotImageRole

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ImagePresignRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filename": "campsite_view.jpg",
                "content_type": "image/jpeg",
                "role": "detail",
            }
        }
    )

    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    role: SpotImageRole = SpotImageRole.DETAIL

    @field_validator("content_type")
    @classmethod
    def _validate_content_type(cls, v: str) -> str:
        if v not in ALLOWED_CONTENT_TYPES:
            allowed = ", ".join(sorted(ALLOWED_CONTENT_TYPES))
            raise ValueError(f"content_type must be one of: {allowed}")
        return v


class ImagePresignResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "upload_url": "https://vivac-images.s3.ap-northeast-2.amazonaws.com/spots/3NwZzKR8jXjA2yLwv9mHhP/nQ7vXH2qzT4Rk8dWmPzYbC.jpg?X-Amz-Signature=...",
                "s3_key": "spots/3NwZzKR8jXjA2yLwv9mHhP/nQ7vXH2qzT4Rk8dWmPzYbC.jpg",
                "expires_in": 3600,
            }
        }
    )

    # 클라이언트는 이 URL로 S3에 직접 PUT 업로드한 뒤 s3_key로 등록을 호출한다.
    upload_url: str
    s3_key: str
    expires_in: int


class SpotImageRegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "s3_key": "spots/3NwZzKR8jXjA2yLwv9mHhP/nQ7vXH2qzT4Rk8dWmPzYbC.jpg",
                "role": "detail",
                "sort_order": 0,
                "is_public": True,
                "content_type": "image/jpeg",
            }
        }
    )

    # presign 응답으로 받은 키를 그대로 전달한다.
    s3_key: str = Field(min_length=1)
    role: SpotImageRole = SpotImageRole.DETAIL
    sort_order: int = 0
    is_public: bool = True
    content_type: str | None = None


class SpotImageOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "8HgJ4mZ2pQeYtRk6vLxWfA",
                "role": "detail",
                "sort_order": 0,
                "is_public": True,
                "url": "https://cdn.vivac.app/spots/3NwZzKR8jXjA2yLwv9mHhP/nQ7vXH2qzT4Rk8dWmPzYbC.jpg",
            }
        },
    )

    uid: str
    role: SpotImageRole
    sort_order: int
    is_public: bool
    url: str
