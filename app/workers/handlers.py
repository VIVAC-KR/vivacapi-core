from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import JobType

JobHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]
"""핸들러 시그니처: (db, payload) -> result dict"""


# JobType → 핸들러 매핑. 실제 핸들러는 후속 이슈(VVC-98, VVC-100)에서 등록된다.
HANDLERS: dict[JobType, JobHandler] = {}
