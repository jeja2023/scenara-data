from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI

from scenara_data import __version__
from scenara_data.config import load_settings

SETTINGS = load_settings()

app = FastAPI(
    title="Scenara Data",
    version=__version__,
    description="Dataset lifecycle domain service for the Scenara platform.",
)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": SETTINGS.service_name,
        "version": __version__,
        "maturity": SETTINGS.maturity,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
