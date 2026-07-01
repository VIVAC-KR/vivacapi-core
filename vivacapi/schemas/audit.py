from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FieldChange(BaseModel):
    before: Any = None
    after: Any = None


class AuditLogEntry(BaseModel):
    changed_at: datetime
    action: str  # INSERT / UPDATE / DELETE
    changed_by: str | None  # 유저 uid (없으면 워커/시스템 변경)
    changed_by_name: str | None  # 화면 표시용 이름
    changes: dict[str, FieldChange]  # 바뀐 필드만
