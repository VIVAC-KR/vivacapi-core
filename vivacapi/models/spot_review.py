from datetime import datetime

import shortuuid
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class SpotReview(Base):
    __tablename__ = "spot_reviews"
    __table_args__ = (
        CheckConstraint("uid ~ '^[0-9A-Za-z]{22}$'", name="ck_spot_reviews_uid_format"),
        CheckConstraint(
            "rating >= 0 AND rating <= 10", name="check_review_rating_range"
        ),
        # soft delete된 리뷰는 슬롯을 점유하지 않도록 활성 리뷰에만 유일성을 강제한다.
        Index(
            "uq_spot_user_review_active",
            "spot_uid",
            "user_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    spot_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("spots.uid"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), nullable=False, index=True
    )

    # 0~10, 반점 단위(=별 0.5개). 프론트에서 10점=별5개로 매핑.
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
