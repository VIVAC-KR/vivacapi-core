from datetime import datetime

import shortuuid
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class SpotReview(Base):
    __tablename__ = "spot_reviews"
    __table_args__ = (
        UniqueConstraint("spot_uid", "user_id", name="uq_spot_user_review"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="check_review_rating_range"),
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

    rating: Mapped[float] = mapped_column(Float, nullable=False)
    content: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
