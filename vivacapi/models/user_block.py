from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class UserBlock(Base):
    """blocker_uid가 blocked_uid를 차단. 차단 관계는 신규 DIRECT 대화 생성/메시지 전송을 막는 데 쓰인다."""

    __tablename__ = "user_blocks"
    __table_args__ = (
        CheckConstraint(
            "blocker_uid <> blocked_uid", name="ck_user_blocks_no_self_block"
        ),
    )

    blocker_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), primary_key=True
    )
    blocked_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("users.uid"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
