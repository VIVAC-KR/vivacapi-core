from datetime import datetime
from enum import StrEnum

import shortuuid
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class GroupVisibility(StrEnum):
    """PRIVATE는 owner만 접근(멤버 초대 불가). PUBLIC은 비로그인 포함 누구나 조회 가능.

    INVITE_ONLY는 PRIVATE와 읽기 권한 체크 로직은 동일(멤버만 조회 가능)하고,
    멤버 초대 허용 여부에서만 갈린다.
    """

    PRIVATE = "private"
    INVITE_ONLY = "invite_only"
    PUBLIC = "public"


class GroupRole(StrEnum):
    """VIEWER < CONTRIBUTOR < EDITOR < OWNER 순으로 권한이 누적된다.

    OWNER는 한 그룹에 여러 명 있을 수 있다(공동 소유).
    """

    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    EDITOR = "editor"
    OWNER = "owner"


class SpotGroup(Base):
    __tablename__ = "spot_groups"
    __table_args__ = (
        CheckConstraint("uid ~ '^[0-9A-Za-z]{22}$'", name="ck_spot_groups_uid_format"),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    visibility: Mapped[GroupVisibility] = mapped_column(
        Enum(
            GroupVisibility,
            name="group_visibility",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=GroupVisibility.PRIVATE,
        server_default=GroupVisibility.PRIVATE.value,
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SpotGroupMember(Base):
    __tablename__ = "spot_group_members"

    group_uid: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("spot_groups.uid", ondelete="CASCADE"),
        primary_key=True,
    )
    user_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), primary_key=True, index=True
    )
    role: Mapped[GroupRole] = mapped_column(
        Enum(
            GroupRole,
            name="group_role",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    invited_by_uid: Mapped[str | None] = mapped_column(
        String(22), ForeignKey("users.uid"), nullable=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SpotGroupSpot(Base):
    __tablename__ = "spot_group_spots"

    group_uid: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("spot_groups.uid", ondelete="CASCADE"),
        primary_key=True,
    )
    spot_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("spots.uid"), primary_key=True
    )
    added_by_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), nullable=False
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
