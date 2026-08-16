from __future__ import annotations

import httpx
import pytest

from scenara_data.api.app import app


@pytest.mark.asyncio
async def test_health_reports_seed_maturity_and_rfc3339_time() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "scenara-data"
    assert payload["maturity"] == "implemented"
    assert payload["timestamp"].endswith("Z")
