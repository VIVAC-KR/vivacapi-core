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
