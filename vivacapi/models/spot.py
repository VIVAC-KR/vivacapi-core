from datetime import datetime
from enum import StrEnum

import shortuuid
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class PipelineStatus(StrEnum):
    """데이터 파이프라인 진행 상태. PUBLISHED만 공개 API에 노출된다.

    DB는 String + CHECK로 저장 (native enum은 값 추가 시 마이그레이션 부담).
    """

    RAW = "RAW"
    ENRICHED = "ENRICHED"
    CURATED = "CURATED"
    REVIEWED = "REVIEWED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


class Spot(Base):
    __tablename__ = "spots"
    __table_args__ = (
        CheckConstraint(
            "uid ~ '^[0-9A-Za-z]{22}$'", name="ck_spots_uid_format"
        ),
        UniqueConstraint("source", "external_id", name="uq_spots_source_external_id"),
        CheckConstraint(
            "pipeline_status IN "
            "('RAW', 'ENRICHED', 'CURATED', 'REVIEWED', 'PUBLISHED', 'REJECTED')",
            name="ck_spots_pipeline_status",
        ),
        CheckConstraint(
            "trust_tier BETWEEN 1 AND 3", name="ck_spots_trust_tier"
        ),
        # 공개 API는 PUBLISHED만 조회하므로 partial index로 커버
        Index(
            "ix_spots_published_uid",
            "uid",
            postgresql_where="pipeline_status = 'PUBLISHED'",
        ),
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

    pipeline_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=PipelineStatus.RAW.value
    )
    # 데이터 신뢰도 등급 (1=공식+완비, 2=일부 누락/교차확인, 3=미검증). 판정 전 NULL.
    trust_tier: Mapped[int | None] = mapped_column(SmallInteger)

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
