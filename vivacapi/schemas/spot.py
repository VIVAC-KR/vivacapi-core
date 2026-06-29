from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpotListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str


class SpotDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str
    address: str | None
    website_url: str | None


class SpotListResponse(BaseModel):
    items: list[SpotListItem]
    next_cursor: str | None
    has_more: bool


class SpotBulkRow(BaseModel):
    source: str | None = None
    external_id: str | None = None
    title: str
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

    rating_avg: float = 0.0
    review_count: int = 0

    website_url: str | None = None
    booking_url: str | None = None
    features: str | None = None
    category: list[str] | None = None
    total_area_m2: float | None = None
    has_liability_insurance: bool | None = None


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
    updated_at: datetime | None


class SpotAdminDetail(BaseModel):
    """편집 폼의 데이터 소스. 모든 컬럼을 그대로 노출."""

    model_config = ConfigDict(from_attributes=True)

    uid: str
    source: str | None
    external_id: str | None
    title: str
    address: str | None
    address_detail: str | None
    region_province: str | None
    region_city: str | None
    postal_code: str | None
    phone: str | None
    description: str | None
    tagline: str | None

    latitude: float | None
    longitude: float | None
    altitude: float | None

    unit_count: int | None
    is_fee_required: bool | None
    is_pet_allowed: bool | None
    pet_policy: str | None

    has_equipment_rental: list[str] | None
    themes: list[str] | None
    fire_pit_type: str | None
    amenities: list[str] | None
    nearby_facilities: list[str] | None
    camp_sight_type: str | None

    rating_avg: float
    review_count: int

    website_url: str | None
    booking_url: str | None
    features: str | None
    category: list[str] | None
    total_area_m2: float | None
    has_liability_insurance: bool | None

    created_at: datetime | None
    updated_at: datetime | None


class SpotUpdate(BaseModel):
    """부분 수정. 전달된 필드만 반영(exclude_unset).

    source/external_id(upsert 키)와 rating_avg/review_count(리뷰 파생값)는
    수정 대상에서 제외한다.
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
