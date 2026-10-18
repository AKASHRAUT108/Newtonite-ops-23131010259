"""Stale version → 409, item unchanged. Fresh version → 200, version bumped."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_stale_update_rejected(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][0]
    h = {"Authorization": f"Bearer {tokens['member']}"}

    ok = await client.patch(
        f"/items/{item_id}",
        json={"expected_version": 1, "priority": "low"},
        headers=h,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["version"] == 2
    assert ok.json()["priority"] == "low"

    stale = await client.patch(
        f"/items/{item_id}",
        json={"expected_version": 1, "priority": "urgent"},
        headers=h,
    )
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert "stale version" in detail["detail"]
    assert detail["current"]["version"] == 2
    assert detail["current"]["status"] == "open"

    # Confirm the item didn't change
    fetched = await client.get(f"/items/{item_id}", headers=h)
    assert fetched.status_code == 200
    assert fetched.json()["priority"] == "low"  # first update stuck
    assert fetched.json()["version"] == 2