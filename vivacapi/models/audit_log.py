from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class AuditLog(Base):
    """DB 트리거가 채우는 감사 로그. 앱에서는 읽기 전용으로만 다룬다."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    row_uid: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    old_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_by: Mapped[str | None] = mapped_column(String)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
