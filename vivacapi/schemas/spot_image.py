from pydantic import BaseModel, ConfigDict, Field, field_validator

from vivacapi.models.spot_image import SpotImageRole

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ImagePresignRequest(BaseModel):
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
    # 클라이언트는 이 URL로 S3에 직접 PUT 업로드한 뒤 s3_key로 등록을 호출한다.
    upload_url: str
    s3_key: str
    expires_in: int


class SpotImageRegisterRequest(BaseModel):
    # presign 응답으로 받은 키를 그대로 전달한다.
    s3_key: str = Field(min_length=1)
    role: SpotImageRole = SpotImageRole.DETAIL
    sort_order: int = 0
    is_public: bool = True
    content_type: str | None = None


class SpotImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    role: SpotImageRole
    sort_order: int
    is_public: bool
    url: str
