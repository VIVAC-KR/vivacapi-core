from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FieldChange(BaseModel):
    before: Any = None
    after: Any = None


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "changed_at": "2026-07-10T09:00:00Z",
                "action": "UPDATE",
                "changed_by": "user_staff01",
                "changed_by_name": "김스태프",
                "changes": {
                    "pipeline_status": {"before": "ENRICHED", "after": "CURATED"}
                },
            }
        }
    )

    changed_at: datetime
    action: str  # INSERT / UPDATE / DELETE
    changed_by: str | None  # 유저 uid (없으면 워커/시스템 변경)
    changed_by_name: str | None  # 화면 표시용 이름
    changes: dict[str, FieldChange]  # 바뀐 필드만
