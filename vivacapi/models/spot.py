from datetime import datetime

import shortuuid
from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class Spot(Base):
    __tablename__ = "spots"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_spots_source_external_id"),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    source: Mapped[str | None] = mapped_column(String, index=True)
    external_id: Mapped[str | None] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, index=True)
    address: Mapped[str | None] = mapped_column(String)
    address_detail: Mapped[str | None] = mapped_column(String)
    region_province: Mapped[str | None] = mapped_column(String, index=True)
    region_city: Mapped[str | None] = mapped_column(String, index=True)
    postal_code: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    tagline: Mapped[str | None] = mapped_column(String)

    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    altitude: Mapped[float | None] = mapped_column(Float)

    unit_count: Mapped[int | None] = mapped_column(Integer)
    is_fee_required: Mapped[bool | None] = mapped_column()
    is_pet_allowed: Mapped[bool | None] = mapped_column()
    pet_policy: Mapped[str | None] = mapped_column(String)

    has_equipment_rental: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    themes: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    fire_pit_type: Mapped[str | None] = mapped_column(String)
    amenities: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    nearby_facilities: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    camp_sight_type: Mapped[str | None] = mapped_column(String)

    rating_avg: Mapped[float] = mapped_column(Float, index=True)
    review_count: Mapped[int] = mapped_column(Integer)

    website_url: Mapped[str | None] = mapped_column(String)
    booking_url: Mapped[str | None] = mapped_column(String)
    features: Mapped[str | None] = mapped_column(String)
    category: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    total_area_m2: Mapped[float | None] = mapped_column(Float)
    has_liability_insurance: Mapped[bool | None] = mapped_column()

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
