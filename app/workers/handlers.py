from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import JobType
from app.workers.spot_business_info_bulk import (
    spot_business_info_bulk_upsert_handler,
)
from app.workers.spots_bulk import spots_bulk_upsert_handler

JobHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]
"""핸들러 시그니처: (db, payload) -> result dict"""


HANDLERS: dict[JobType, JobHandler] = {
    JobType.SPOTS_BULK_UPSERT: spots_bulk_upsert_handler,
    JobType.SPOT_BUSINESS_INFO_BULK_UPSERT: spot_business_info_bulk_upsert_handler,
}
