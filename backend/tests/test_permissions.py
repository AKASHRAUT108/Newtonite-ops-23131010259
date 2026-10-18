"""Cross-team access is forbidden; resource-level auth enforced."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_outside_team_cannot_read(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][0]  # belongs to Platform
    h = {"Authorization": f"Bearer {tokens['outside']}"}  # Payments team
    r = await client.get(f"/items/{item_id}", headers=h)
    assert r.status_code in (403, 404)


@pytest.mark.asyncio
async def test_viewer_cannot_update(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][0]
    h = {"Authorization": f"Bearer {tokens['viewer']}"}
    r = await client.patch(
        f"/items/{item_id}",
        json={"expected_version": 1, "priority": "urgent"},
        headers=h,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_claim(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][2]
    h = {"Authorization": f"Bearer {tokens['viewer']}"}
    r = await client.post(f"/items/{item_id}/claim", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_member_can_create(client: AsyncClient, seeded: dict, tokens: dict):
    h = {"Authorization": f"Bearer {tokens['member']}"}
    payload = {"title": "new one", "type": "incident", "priority": "high", "team_id": seeded["platform_id"]}
    r = await client.post("/items", json=payload, headers=h)
    assert r.status_code == 201