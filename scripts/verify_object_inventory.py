"""验证业务对象桶的版本控制与 SHA-256 元数据，可作为备份后巡检。"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass

from scenara_data.config import Settings, load_settings


@dataclass(frozen=True, slots=True)
class BucketVerification:
    bucket: str
    versioning_enabled: bool
    object_count: int
    missing_checksum_count: int
    checksum_mismatch_count: int


def _client(settings: Settings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        region_name=settings.object_storage_region,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
    )


def verify_bucket(client: object, bucket: str, *, verify_content: bool) -> BucketVerification:
    versioning = client.get_bucket_versioning(Bucket=bucket)
    paginator = client.get_paginator("list_objects_v2")
    count = missing_checksum = checksum_mismatch = 0
    for page in paginator.paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            key = item["Key"]
            count += 1
            response = client.head_object(Bucket=bucket, Key=key)
            expected = response.get("Metadata", {}).get("sha256")
            if not expected:
                missing_checksum += 1
                continue
            if verify_content:
                content = client.get_object(Bucket=bucket, Key=key)["Body"].read()
                if hashlib.sha256(content).hexdigest() != expected:
                    checksum_mismatch += 1
    return BucketVerification(
        bucket=bucket,
        versioning_enabled=versioning.get("Status") == "Enabled",
        object_count=count,
        missing_checksum_count=missing_checksum,
        checksum_mismatch_count=checksum_mismatch,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="巡检 S3 业务桶版本控制与对象校验和")
    parser.add_argument("--bucket", action="append", default=[])
    parser.add_argument("--verify-content", action="store_true", help="下载对象并重新计算 SHA-256")
    parser.add_argument("--allow-missing-checksum", action="store_true")
    arguments = parser.parse_args()
    settings = load_settings()
    buckets = arguments.bucket or [
        settings.dataset_bucket,
        settings.manifest_bucket,
        settings.import_bucket,
        settings.export_bucket,
        settings.artifact_bucket,
        settings.backup_bucket,
    ]
    client = _client(settings)
    results = [verify_bucket(client, bucket, verify_content=arguments.verify_content) for bucket in buckets]
    failing = [
        result
        for result in results
        if not result.versioning_enabled
        or result.checksum_mismatch_count
        or (result.missing_checksum_count and not arguments.allow_missing_checksum)
    ]
    print(json.dumps({"buckets": [asdict(result) for result in results]}, ensure_ascii=False, indent=2))
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
