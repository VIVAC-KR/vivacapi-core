import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SpotSort(StrEnum):
    POPULAR = "popular"
    LATEST = "latest"
    RATING = "rating"


class SpotListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    title: str
    tagline: str | None
    region_province: str | None
    region_city: str | None
    rating_avg: float
    review_count: int
    themes: list[str] | None


class SpotDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    title: str
    tagline: str | None
    description: str | None

    address: str | None
    address_detail: str | None
    region_province: str | None
    region_city: str | None
    postal_code: str | None

    latitude: float | None
    longitude: float | None
    altitude: float | None

    phone: str | None
    website_url: str | None
    booking_url: str | None

    unit_count: int | None
    total_area_m2: float | None

    is_fee_required: bool | None
    is_pet_allowed: bool | None
    pet_policy: str | None
    has_liability_insurance: bool | None

    themes: list[str] | None
    category: list[str] | None
    camp_sight_type: str | None
    fire_pit_type: str | None
    features: str | None

    amenities: list[str] | None
    nearby_facilities: list[str] | None
    has_equipment_rental: list[str] | None

    rating_avg: float
    review_count: int

    created_at: datetime | None
    updated_at: datetime | None


class SpotListResponse(BaseModel):
    items: list[SpotListItem]
    next_cursor: str | None
    has_more: bool
    total: int | None = None
