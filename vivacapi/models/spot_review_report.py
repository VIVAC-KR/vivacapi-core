from datetime import datetime

import shortuuid
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class SpotReviewReport(Base):
    __tablename__ = "spot_review_reports"
    __table_args__ = (
        CheckConstraint(
            "uid ~ '^[0-9A-Za-z]{22}$'", name="ck_spot_review_reports_uid_format"
        ),
        UniqueConstraint("review_uid", "reporter_user_uid", name="uq_review_reporter"),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    review_uid: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("spot_reviews.uid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reporter_user_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
