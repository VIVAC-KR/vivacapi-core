from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class SpotOptionField(StrEnum):
    """관리형 화이트리스트를 쓰는 spots의 배열 컬럼들. 값은 실제 컬럼명과 동일 —
    crud에서 getattr(Spot, field)로 바로 매칭하기 위함."""

    CATEGORY = "category"
    AMENITIES = "amenities"
    NEARBY_FACILITIES = "nearby_facilities"
    HAS_EQUIPMENT_RENTAL = "has_equipment_rental"


class SpotFieldOption(Base):
    """spots의 배열 필드(category/amenities/nearby_facilities/has_equipment_rental)에
    들어갈 수 있는 값의 화이트리스트. (field, code)가 복합 자연키 — code가 곧
    spots 배열 원소값이라 조회 시 join 없이 그대로 매칭한다.
    """

    __tablename__ = "spot_field_options"
    __table_args__ = (
        CheckConstraint(
            "code ~ '^[A-Z][A-Z0-9_]*$'", name="ck_spot_field_options_code_format"
        ),
    )

    field: Mapped[str] = mapped_column(String(30), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label_ko: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
