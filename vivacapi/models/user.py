from datetime import datetime
from enum import StrEnum

import shortuuid
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class MembershipTier(StrEnum):
    FREE = "free"
    MEMBER = "member"


class StaffRole(StrEnum):
    """staff 내 세부 권한 등급. is_staff=False인 사용자에게는 의미 없다.

    STAFF < MANAGER < SUPERUSER 순으로 권한이 누적된다.
    """

    STAFF = "staff"
    MANAGER = "manager"
    SUPERUSER = "superuser"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "uid ~ '^[0-9A-Za-z]{22}$'", name="ck_users_uid_format"
        ),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(100))
    picture: Mapped[str | None] = mapped_column(String(2048))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_staff: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    staff_role: Mapped[StaffRole] = mapped_column(
        Enum(
            StaffRole,
            name="staff_role",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=StaffRole.STAFF,
        server_default=StaffRole.STAFF.value,
    )
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
