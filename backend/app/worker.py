"""
Worker process. Runs as a separate container.

Loop:
  1. Atomically claim one pending job (FOR UPDATE SKIP LOCKED)
  2. Execute handler
  3. On success: mark 'done'
  4. On failure: increment attempts, back off, or mark 'failed' after max_attempts

Handlers are idempotent: if a job runs twice, the effect happens once.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import Job

logger = logging.getLogger("worker")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

POLL_INTERVAL_SECONDS = 2
MAX_BACKOFF_SECONDS = 60


# ---------- handlers (idempotent) ----------

async def handle_notify_assignee(session: AsyncSession, payload: dict) -> None:
    """
    Idempotent: appending to a text log is repeat-safe.
    In production this would send an email/Slack — the real world would
    enforce idempotency via a unique (item_id, recipient) row before send.
    Here we just log.
    """
        raise RuntimeError("forced failure to demonstrate retries")
    item_id = payload.get("item_id")
    assignee_id = payload.get("assignee_id")
    logger.info("NOTIFY assignee=%s item=%s", assignee_id, item_id)


HANDLERS = {
    "notify_assignee": handle_notify_assignee,
}


# ---------- worker loop ----------

async def _claim_one_job(session: AsyncSession) -> Job | None:
    """
    Atomically lock one pending job whose run_at <= now.
    FOR UPDATE SKIP LOCKED lets multiple workers run without racing.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(Job)
        .where(
            Job.status == "pending",
            Job.run_at <= now,
            Job.attempts < Job.max_attempts,
        )
        .order_by(Job.run_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        return None

    # Mark running in the same txn as the lock
    job.status = "running"
    job.attempts += 1
    await session.commit()
    await session.refresh(job)
    return job


async def _handle_job(job: Job) -> None:
    handler = HANDLERS.get(job.type)
    if handler is None:
        raise ValueError(f"no handler for job type {job.type!r}")

    async with AsyncSessionLocal() as session:
        # Re-attach the job to a fresh session
        db_job = await session.get(Job, job.id)
        if db_job is None:
            logger.warning("job %s disappeared", job.id)
            return
        try:
            await handler(session, db_job.payload)
        except Exception as exc:  # noqa: BLE001
            await _mark_failed(session, db_job, str(exc))
            raise
        else:
            db_job.status = "done"
            db_job.last_error = None
            await session.commit()
            logger.info("job %s done (%s, attempt %d)", db_job.id, db_job.type, db_job.attempts)


async def _mark_failed(session: AsyncSession, job: Job, error: str) -> None:
    job.last_error = error[:1000]
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        logger.error("job %s FAILED permanently after %d attempts: %s",
                     job.id, job.attempts, error[:200])
    else:
        # Exponential backoff: 2^attempts seconds
        backoff = min(MAX_BACKOFF_SECONDS, 2 ** job.attempts)
        job.status = "pending"
        job.run_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
        logger.warning("job %s attempt %d failed (%s); retry in %ds",
                       job.id, job.attempts, error[:200], backoff)
    await session.commit()


async def run_forever() -> None:
    logger.info("worker starting; poll interval=%ds", POLL_INTERVAL_SECONDS)
    while True:
        try:
            async with AsyncSessionLocal() as session:
                job = await _claim_one_job(session)
            if job is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
            try:
                await _handle_job(job)
            except Exception:  # noqa: BLE001
                # already logged + marked failed inside _handle_job
                pass
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("worker loop error; sleeping 5s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("worker stopped")