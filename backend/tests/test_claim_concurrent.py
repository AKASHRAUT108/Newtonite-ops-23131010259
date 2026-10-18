"""Two users claim the same item in parallel — exactly one wins."""

import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_two_claims_one_wins(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][0]

    async def claim(token: str):
        return await client.post(
            f"/items/{item_id}/claim",
            headers={"Authorization": f"Bearer {token}"},
        )

    r1, r2 = await asyncio.gather(
        claim(tokens["lead"]),
        claim(tokens["member"]),
    )

    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409], f"expected one 200 + one 409, got {codes}"

    # The 409 must carry the current item snapshot
    failed = r1 if r1.status_code == 409 else r2
    payload = failed.json()["detail"]
    assert payload["detail"] == "item already claimed"
    assert payload["current"]["id"] == item_id
    assert payload["current"]["version"] == 2


@pytest.mark.asyncio
async def test_claim_twice_by_same_user_second_is_409(client: AsyncClient, seeded: dict, tokens: dict):
    item_id = seeded["items"][1]
    h = {"Authorization": f"Bearer {tokens['member']}"}

    first = await client.post(f"/items/{item_id}/claim", headers=h)
    assert first.status_code == 200

    second = await client.post(f"/items/{item_id}/claim", headers=h)
    assert second.status_code == 409