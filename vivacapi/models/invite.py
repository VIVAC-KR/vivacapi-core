from datetime import datetime
from enum import StrEnum

import shortuuid
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base
from vivacapi.models.spot_group import GroupRole


class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class Invite(Base):
    """공유 링크 기반 초대. group_uid가 있으면 그룹 초대, 없으면 일반 앱 리퍼럴이다.

    1회용 — 수락되면 status가 ACCEPTED로 바뀌어 재사용 불가. 여러 명 초대하려면
    초대장을 여러 개 발급한다.
    """

    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint("uid ~ '^[0-9A-Za-z]{22}$'", name="ck_invites_uid_format"),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    inviter_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), nullable=False, index=True
    )
    group_uid: Mapped[str | None] = mapped_column(
        String(22),
        ForeignKey("spot_groups.uid", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    group_role: Mapped[GroupRole | None] = mapped_column(
        Enum(
            GroupRole,
            name="group_role",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )
    status: Mapped[InviteStatus] = mapped_column(
        Enum(
            InviteStatus,
            name="invite_status",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=InviteStatus.PENDING,
        server_default=InviteStatus.PENDING.value,
    )
    accepted_by_uid: Mapped[str | None] = mapped_column(
        String(22), ForeignKey("users.uid"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
