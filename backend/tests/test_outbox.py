"""Claim enqueues a job in the same transaction; history is logged."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityEvent, Job


@pytest.mark.asyncio
async def test_claim_enqueues_job(client: AsyncClient, seeded: dict, tokens: dict, session: AsyncSession):
    item_id = seeded["items"][0]
    h = {"Authorization": f"Bearer {tokens['member']}"}

    r = await client.post(f"/items/{item_id}/claim", headers=h)
    assert r.status_code == 200

    # Job row exists
    job = await session.scalar(select(Job).where(Job.type == "notify_assignee"))
    assert job is not None
    assert job.status == "pending"
    assert job.payload["item_id"] == item_id
    assert job.max_attempts == 3


@pytest.mark.asyncio
async def test_claim_writes_activity_in_same_txn(
    client: AsyncClient, seeded: dict, tokens: dict, db_engine,
):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    item_id = seeded["items"][0]
    h = {"Authorization": f"Bearer {tokens['member']}"}

    r = await client.post(f"/items/{item_id}/claim", headers=h)
    assert r.status_code == 200

    # Fresh session so we're guaranteed to see the claim's committed data.
    SessionLocal = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as fresh:
        kinds = (await fresh.execute(
            select(ActivityEvent.kind).where(ActivityEvent.item_id == item_id)
        )).scalars().all()

    assert "claimed" in kinds, f"got kinds={kinds}"
    assert kinds.count("created") == 1