"""Transactional outbox. Enqueue a job INSIDE the caller's transaction.

Callers do:

    await enqueue(session, "notify_assignee", {"item_id": ..., "assignee_id": ...})
    await session.commit()

Both the item mutation and the job row go in the same commit.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job


async def enqueue(
    session: AsyncSession,
    job_type: str,
    payload: dict,
    *,
    delay_seconds: int = 0,
) -> Job:
    run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    job = Job(
        type=job_type,
        payload=payload,
        status="pending",
        attempts=0,
        max_attempts=3,
        run_at=run_at,
    )
    session.add(job)
    await session.flush()
    return job