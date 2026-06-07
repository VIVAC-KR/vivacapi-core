from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.job import Job


async def get_job_by_id(db: AsyncSession, job_id: str) -> Job | None:
    result = await db.execute(select(Job).where(Job.uid == job_id))
    return result.scalar_one_or_none()
