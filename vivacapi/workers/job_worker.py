import asyncio
import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vivacapi.core.database import AsyncSessionLocal
from vivacapi.models.job import Job, JobStatus
from vivacapi.workers.handlers import HANDLERS

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 2.0


async def cleanup_orphaned_jobs(db: AsyncSession) -> int:
    """status='running' 상태로 남아있는 job을 'failed' (error='orphaned')로 전환한다.
    인스턴스가 처리 중 죽어서 좀비 상태가 된 job을 부팅 시 1회 정리한다.
    """
    result = await db.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING)
        .values(
            status=JobStatus.FAILED,
            error="orphaned",
            finished_at=datetime.now(timezone.utc),
        )
        .returning(Job.uid)
    )
    rows = result.all()
    await db.commit()
    return len(rows)


async def claim_next_job(db: AsyncSession) -> Job | None:
    """PENDING job 1건을 락 잡고 RUNNING으로 전환한다.

    FOR UPDATE SKIP LOCKED로 다중 워커 환경에서도 충돌 없이 1건씩 분배된다.
    잡을 게 없으면 None.
    """
    result = await db.execute(
        select(Job)
        .where(Job.status == JobStatus.PENDING)
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return job


async def process_job(db: AsyncSession, job: Job) -> None:
    """핸들러를 dispatch하고 결과를 기록한다. 예외 시 traceback을 `error`에 저장."""
    handler = HANDLERS.get(job.type)
    if handler is None:
        job.status = JobStatus.FAILED
        job.error = f"No handler registered for {job.type.value}"
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return

    try:
        result = await handler(db, job.payload)
        job.status = JobStatus.SUCCEEDED
        job.result = result
    except Exception:
        job.status = JobStatus.FAILED
        job.error = traceback.format_exc()
        logger.exception("Job %s failed", job.uid)
    finally:
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()


async def run_worker_cycle(
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> bool:
    """1사이클: claim + process. 처리한 게 있으면 True, 없으면 False.

    claim과 process를 별도 트랜잭션으로 분리해 락을 빠르게 해제하고,
    작업 중에도 다른 곳에서 job 상태를 polling할 수 있게 한다.
    """
    async with session_factory() as session:
        job = await claim_next_job(session)

    if job is None:
        return False

    async with session_factory() as session:
        reloaded = await session.execute(select(Job).where(Job.uid == job.uid))
        job = reloaded.scalar_one()
        await process_job(session, job)

    return True


async def job_worker_loop(
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    """무한 루프 워커. cancel 시 정상 종료."""
    logger.info("Job worker started")
    try:
        while True:
            try:
                processed = await run_worker_cycle(session_factory)
                if not processed:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Job worker cycle error")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("Job worker cancelled")
        raise


async def startup_orphan_cleanup(
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> int:
    """부팅 시 호출되는 entrypoint: 새 세션으로 cleanup_orphaned_jobs 실행."""
    async with session_factory() as session:
        return await cleanup_orphaned_jobs(session)
