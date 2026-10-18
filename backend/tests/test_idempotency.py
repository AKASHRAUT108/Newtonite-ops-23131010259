"""Same Idempotency-Key twice → one item, same response ID."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_same_key_creates_one_item(client: AsyncClient, seeded: dict, tokens: dict):
    payload = {
        "title": "idem test",
        "type": "task",
        "priority": "medium",
        "team_id": seeded["platform_id"],
    }
    h = {
        "Authorization": f"Bearer {tokens['member']}",
        "Idempotency-Key": "test-key-1",
    }

    r1 = await client.post("/items", json=payload, headers=h)
    r2 = await client.post("/items", json=payload, headers=h)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    # Only one item created
    listing = await client.get("/items?q=idem", headers={"Authorization": f"Bearer {tokens['member']}"})
    assert listing.status_code == 200
    matches = [i for i in listing.json()["items"] if i["title"] == "idem test"]
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_different_payload_same_key_rejected(client: AsyncClient, seeded: dict, tokens: dict):
    h = {
        "Authorization": f"Bearer {tokens['member']}",
        "Idempotency-Key": "test-key-2",
    }
    p1 = {"title": "A", "type": "task", "priority": "medium", "team_id": seeded["platform_id"]}
    p2 = {"title": "B", "type": "task", "priority": "medium", "team_id": seeded["platform_id"]}

    assert (await client.post("/items", json=p1, headers=h)).status_code == 201
    r2 = await client.post("/items", json=p2, headers=h)
    assert r2.status_code == 409
    assert "different payload" in r2.json()["detail"]