from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vivacapi.models.spot import PipelineStatus


class SpotListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str
    trust_tier: int | None
    thumbnail_url: str | None
    region_short: str | None
    category: list[str] | None


class SpotDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str
    address: str | None
    website_url: str | None
    trust_tier: int | None


class SpotListResponse(BaseModel):
    items: list[SpotListItem]
    next_cursor: str | None
    has_more: bool


class SpotEditableFields(BaseModel):
    """spot의 수정 가능 컬럼 공통 정의.

    BulkRow/AdminDetail/Update가 공유한다. upsert 키(source/external_id)와
    리뷰 파생값(rating_avg/review_count)은 서브클래스에서 정책대로 추가한다.
    """

    title: str | None = None
    address: str | None = None
    address_detail: str | None = None
    region_province: str | None = None
    region_city: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    description: str | None = None
    tagline: str | None = None

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None

    unit_count: int | None = None
    is_fee_required: bool | None = None
    is_pet_allowed: bool | None = None
    pet_policy: str | None = None

    has_equipment_rental: list[str] | None = None
    themes: list[str] | None = None
    fire_pit_type: str | None = None
    amenities: list[str] | None = None
    nearby_facilities: list[str] | None = None
    camp_sight_type: str | None = None

    website_url: str | None = None
    booking_url: str | None = None
    features: str | None = None
    category: list[str] | None = None
    total_area_m2: float | None = None
    has_liability_insurance: bool | None = None

    pipeline_status: PipelineStatus | None = None
    trust_tier: int | None = Field(None, ge=1, le=3)


class SpotBulkRow(SpotEditableFields):
    title: str  # bulk 입력에서는 필수
    source: str | None = None
    external_id: str | None = None
    rating_avg: float = 0.0
    review_count: int = 0


class SpotBulkRequest(BaseModel):
    dry_run: bool = False
    rows: list[SpotBulkRow] = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# Internal admin (vivac-console) — 단건 조회/수정
# ---------------------------------------------------------------------------


class SpotAdminListItem(BaseModel):
    """어드민 테이블 행. 목록에서 식별/필터에 필요한 최소 필드만."""

    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str
    source: str | None
    region_province: str | None
    region_city: str | None
    rating_avg: float
    review_count: int
    pipeline_status: PipelineStatus
    trust_tier: int | None
    updated_at: datetime | None


class SpotAdminDetail(SpotEditableFields):
    """편집 폼의 데이터 소스. 모든 컬럼을 그대로 노출."""

    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str
    source: str | None
    external_id: str | None
    rating_avg: float
    review_count: int
    created_at: datetime | None
    updated_at: datetime | None


class SpotUpdate(SpotEditableFields):
    """부분 수정. 전달된 필드만 반영(exclude_unset).

    source/external_id(upsert 키)와 rating_avg/review_count(리뷰 파생값)는
    수정 대상에서 제외한다.
    """


# ---------------------------------------------------------------------------
# 대시보드 통계
# ---------------------------------------------------------------------------


class CountItem(BaseModel):
    key: str
    count: int


class SpotStats(BaseModel):
    total: int
    business_info_total: int
    missing_coordinates: int
    by_source: list[CountItem]
    by_region_province: list[CountItem]
    my_assigned_total: int
    my_completed: int


class SpotAssignmentRequest(BaseModel):
    user_uid: str
    count: int = Field(gt=0, le=1000)


class SpotAssignmentResponse(BaseModel):
    assigned_count: int
