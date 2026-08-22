from datetime import datetime
from enum import StrEnum

import shortuuid
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class ConversationType(StrEnum):
    DIRECT = "direct"
    GROUP = "group"


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "uid ~ '^[0-9A-Za-z]{22}$'", name="ck_conversations_uid_format"
        ),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    type: Mapped[ConversationType] = mapped_column(
        Enum(
            ConversationType,
            name="conversation_type",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConversationParticipant(Base):
    """DIRECT 대화의 재사용 판별(같은 두 유저 조합 존재 여부)은 crud에서 처리한다."""

    __tablename__ = "conversation_participants"

    conversation_uid: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("conversations.uid", ondelete="CASCADE"),
        primary_key=True,
    )
    user_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), primary_key=True, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
