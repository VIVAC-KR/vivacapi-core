from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.job import JobStatus, JobType


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    type: JobType
    status: JobStatus
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
