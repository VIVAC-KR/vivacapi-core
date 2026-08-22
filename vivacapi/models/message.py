from datetime import datetime

import shortuuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("uid ~ '^[0-9A-Za-z]{22}$'", name="ck_messages_uid_format"),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    conversation_uid: Mapped[str] = mapped_column(
        String(22),
        ForeignKey("conversations.uid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), nullable=False
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
