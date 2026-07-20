from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vivacapi.models.spot import PipelineStatus


class SpotListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "spot_a1b2c3",
                "title": "남이섬 오토캠핑장",
                "trust_tier": 2,
                "thumbnail_url": "https://cdn.vivac.app/spots/spot_a1b2c3/thumb.jpg",
                "region_short": "강원",
                "category": ["AUTO_CAMPING"],
            }
        },
    )

    uid: str
    title: str
    trust_tier: int | None
    thumbnail_url: str | None
    region_short: str | None
    category: list[str] | None


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


class SpotDetail(BaseModel):
    """공개 상세 조회 응답. SpotEditableFields를 상속하지 않고 노출 필드를
    명시적으로 나열한다 — pipeline_status/has_liability_insurance 등
    관리자 전용 컬럼이 상속으로 딸려 나가지 않도록 화이트리스트를 유지한다.
    """

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "uid": "spot_a1b2c3",
                "title": "남이섬 오토캠핑장",
                "address": "강원도 춘천시 남산면 남이섬길 1",
                "website_url": "https://namisum.com",
                "trust_tier": 2,
                "tagline": "북한강이 보이는 조용한 오토캠핑장",
                "category": ["AUTO_CAMPING"],
                "themes": ["강변", "반려동물동반"],
                "is_fee_required": True,
                "is_pet_allowed": True,
                "features": "우천 시 일부 사이트 침수 주의",
                "camp_sight_type": "데크",
                "unit_count": 42,
                "total_area_m2": 15000.0,
                "fire_pit_type": "개별 화로대",
                "latitude": 37.7907,
                "longitude": 127.5262,
                "amenities": ["샤워실", "화장실", "전기"],
                "nearby_facilities": ["편의점", "마트"],
                "has_equipment_rental": ["텐트", "테이블"],
                "phone": "033-1234-5678",
                "booking_url": "https://namisum.com/booking",
                "image_url": "https://cdn.vivac.app/spots/spot_a1b2c3/thumb.jpg",
                "rating_avg": 4.5,
                "review_count": 12,
            }
        },
    )

    uid: str
    title: str
    address: str | None
    address_detail: str | None = None
    website_url: str | None
    trust_tier: int | None

    tagline: str | None = None
    category: list[str] | None = None
    themes: list[str] | None = None
    is_fee_required: bool | None = None
    is_pet_allowed: bool | None = None
    features: str | None = None
    camp_sight_type: str | None = None
    unit_count: int | None = None
    total_area_m2: float | None = None
    fire_pit_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    amenities: list[str] | None = None
    nearby_facilities: list[str] | None = None
    has_equipment_rental: list[str] | None = None
    phone: str | None = None
    booking_url: str | None = None
    image_url: str | None = None

    rating_avg: float
    review_count: int


class SpotListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "uid": "spot_a1b2c3",
                        "title": "남이섬 오토캠핑장",
                        "trust_tier": 2,
                        "thumbnail_url": "https://cdn.vivac.app/spots/spot_a1b2c3/thumb.jpg",
                        "region_short": "강원",
                        "category": ["AUTO_CAMPING"],
                    }
                ],
                "next_cursor": "eyJ1aWQiOiJzcG90X2ExYjJjMyJ9",
                "has_more": True,
            }
        }
    )

    items: list[SpotListItem]
    next_cursor: str | None
    has_more: bool


class SpotBulkRow(SpotEditableFields):
    title: str  # bulk 입력에서는 필수
    source: str | None = None
    external_id: str | None = None
    rating_avg: float = 0.0
    review_count: int = 0


class SpotBulkRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dry_run": False,
                "rows": [
                    {
                        "source": "vivac_partner",
                        "external_id": "vp-00123",
                        "title": "남이섬 오토캠핑장",
                        "address": "강원도 춘천시 남산면 남이섬길 1",
                        "region_province": "강원",
                        "region_city": "춘천시",
                        "latitude": 37.7907,
                        "longitude": 127.5262,
                        "category": ["AUTO_CAMPING"],
                        "rating_avg": 4.5,
                        "review_count": 12,
                    }
                ],
            }
        }
    )

    dry_run: bool = False
    rows: list[SpotBulkRow] = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# Internal admin (vivac-console) — 단건 조회/수정
# ---------------------------------------------------------------------------


class SpotAdminListItem(BaseModel):
    """어드민 테이블 행. 목록에서 식별/필터에 필요한 최소 필드만."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "spot_a1b2c3",
                "title": "남이섬 오토캠핑장",
                "source": "vivac_partner",
                "region_province": "강원",
                "region_city": "춘천시",
                "rating_avg": 4.5,
                "review_count": 12,
                "pipeline_status": "ENRICHED",
                "trust_tier": 2,
                "deleted_at": None,
                "updated_at": "2026-07-10T09:00:00Z",
            }
        },
    )

    uid: str
    title: str
    source: str | None
    region_province: str | None
    region_city: str | None
    rating_avg: float
    review_count: int
    pipeline_status: PipelineStatus
    trust_tier: int | None
    deleted_at: datetime | None
    updated_at: datetime | None


class SpotAdminDetail(SpotEditableFields):
    """편집 폼의 데이터 소스. 모든 컬럼을 그대로 노출."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "title": "남이섬 오토캠핑장",
                "address": "강원도 춘천시 남산면 남이섬길 1",
                "region_province": "강원",
                "region_city": "춘천시",
                "phone": "033-1234-5678",
                "category": ["AUTO_CAMPING"],
                "pipeline_status": "ENRICHED",
                "trust_tier": 2,
                "uid": "spot_a1b2c3",
                "source": "vivac_partner",
                "external_id": "vp-00123",
                "rating_avg": 4.5,
                "review_count": 12,
                "assigned_to_uid": "user_staff01",
                "deleted_at": None,
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-07-10T09:00:00Z",
            }
        },
    )

    uid: str
    title: str
    source: str | None
    external_id: str | None
    rating_avg: float
    review_count: int
    assigned_to_uid: str | None
    deleted_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class SpotUpdate(SpotEditableFields):
    """부분 수정. 전달된 필드만 반영(exclude_unset).

    source/external_id(upsert 키)와 rating_avg/review_count(리뷰 파생값)는
    수정 대상에서 제외한다.
    """

    model_config = ConfigDict(
        json_schema_extra={"example": {"pipeline_status": "CURATED", "trust_tier": 2}}
    )


# ---------------------------------------------------------------------------
# 대시보드 통계
# ---------------------------------------------------------------------------


class CountItem(BaseModel):
    key: str
    count: int


class SpotStats(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 1240,
                "business_info_total": 980,
                "missing_coordinates": 15,
                "by_source": [{"key": "vivac_partner", "count": 700}],
                "by_region_province": [{"key": "강원", "count": 320}],
                "my_assigned_total": 8,
                "my_completed": 5,
            }
        }
    )

    total: int
    business_info_total: int
    missing_coordinates: int
    by_source: list[CountItem]
    by_region_province: list[CountItem]
    my_assigned_total: int
    my_completed: int


class SpotAssignmentRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"user_uid": "user_staff01", "count": 20}}
    )

    user_uid: str
    count: int = Field(gt=0, le=1000)


class SpotAssignmentResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"assigned_count": 20}})

    assigned_count: int


class SpotReassignmentRequest(BaseModel):
    user_uid: str | None = None  # None이면 배정 해제
