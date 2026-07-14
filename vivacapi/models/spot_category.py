from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class SpotCategoryOption(Base):
    """spot.category 배열에 들어갈 수 있는 값의 화이트리스트.

    code가 곧 spots.category 배열의 원소값이라 자연키로 쓴다(shortuuid PK 안 씀) —
    조회 시 join 없이 그대로 매칭하기 위함.
    """

    __tablename__ = "spot_category_options"
    __table_args__ = (
        CheckConstraint(
            "code ~ '^[A-Z][A-Z0-9_]*$'", name="ck_spot_category_options_code_format"
        ),
    )

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label_ko: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
