from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "postgresql://scenara_data@127.0.0.1:5432/scenara_data"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/1"
DEFAULT_OBJECT_STORAGE_ENDPOINT = "http://127.0.0.1:9000"
DEFAULT_DATASET_BUCKET = "scenara-datasets"


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "scenara-data"
    maturity: str = "seed"
    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str = DEFAULT_REDIS_URL
    object_storage_endpoint: str = DEFAULT_OBJECT_STORAGE_ENDPOINT
    dataset_bucket: str = DEFAULT_DATASET_BUCKET


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("SCENARA_DATA_DATABASE_URL", DEFAULT_DATABASE_URL),
        redis_url=os.getenv("SCENARA_DATA_REDIS_URL", DEFAULT_REDIS_URL),
        object_storage_endpoint=os.getenv("SCENARA_DATA_S3_ENDPOINT_URL", DEFAULT_OBJECT_STORAGE_ENDPOINT),
        dataset_bucket=os.getenv("SCENARA_DATA_DATASET_BUCKET", DEFAULT_DATASET_BUCKET),
    )
