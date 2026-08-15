from fastapi.testclient import TestClient

from scenara_data.api.app import app


def test_health_reports_seed_maturity_and_rfc3339_time() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "scenara-data"
    assert payload["maturity"] == "seed"
    assert payload["timestamp"].endswith("Z")
