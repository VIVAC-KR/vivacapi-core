from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from vivacapi.models.job import JobStatus, JobType


class JobRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "V1StGXR8Z5jdHi6BUqOB2",
                "type": "spots_bulk_upsert",
                "status": "succeeded",
                "result": {"created": 12, "updated": 3},
                "error": None,
                "created_at": "2026-07-10T09:00:00+09:00",
                "started_at": "2026-07-10T09:00:01+09:00",
                "finished_at": "2026-07-10T09:00:05+09:00",
            }
        },
    )

    uid: str
    type: JobType
    status: JobStatus
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
