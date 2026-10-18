"""Illegal transitions rejected; approval requires LEAD."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_illegal_transition_rejected(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][0]
    h = {"Authorization": f"Bearer {tokens['member']}"}

    r = await client.post(
        f"/items/{item_id}/transition",
        json={"to_status": "closed"},  # open -> closed is illegal
        headers=h,
    )
    assert r.status_code == 422
    assert "illegal transition" in r.json()["detail"]


@pytest.mark.asyncio
async def test_approval_requires_lead(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][1]

    # Walk to awaiting_approval as member
    hm = {"Authorization": f"Bearer {tokens['member']}"}
    assert (await client.post(f"/items/{item_id}/transition", json={"to_status": "in_progress"}, headers=hm)).status_code == 200
    assert (await client.post(f"/items/{item_id}/transition", json={"to_status": "awaiting_approval"}, headers=hm)).status_code == 200

    # Member can't approve
    denied = await client.post(f"/items/{item_id}/transition", json={"to_status": "resolved"}, headers=hm)
    assert denied.status_code == 403

    # Lead can
    hl = {"Authorization": f"Bearer {tokens['lead']}"}
    ok = await client.post(f"/items/{item_id}/transition", json={"to_status": "resolved"}, headers=hl)
    assert ok.status_code == 200
    assert ok.json()["status"] == "resolved"