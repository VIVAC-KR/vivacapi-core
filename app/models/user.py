import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MembershipTier(StrEnum):
    FREE = "free"
    MEMBER = "member"


class User(Base):
    __tablename__ = "users"

    uid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(100))
    picture: Mapped[str | None] = mapped_column(String(2048))
    is_active: Mapped[bool] = mapped_column(default=True)
    membership_tier: Mapped[MembershipTier] = mapped_column(
        Enum(
            MembershipTier,
            name="membership_tier",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=MembershipTier.FREE,
        server_default=MembershipTier.FREE.value,
    )
    identity_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    onboarding_survey_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_identity_verified(self) -> bool:
        return self.identity_verified_at is not None

    @property
    def has_completed_onboarding_survey(self) -> bool:
        return self.onboarding_survey_completed_at is not None
