"""按对象快照清单恢复 S3 对象；默认校验，实际复制必须显式确认。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:  # 支持直接脚本执行与测试模块导入。
    from scripts.backup_object_store import manifest_checksum
except ModuleNotFoundError:  # pragma: no cover - 仅直接脚本执行路径
    from backup_object_store import manifest_checksum
from scenara_data.config import Settings, load_settings


def _client(settings: Settings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        region_name=settings.object_storage_region,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
    )


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    checksum = str(manifest.pop("sha256", ""))
    if len(checksum) != 64 or manifest_checksum(manifest) != checksum:
        raise ValueError("对象快照清单 SHA-256 不一致")
    manifest["sha256"] = checksum
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="恢复对象存储快照")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default="", help="实际恢复时必须填写对象清单 SHA-256")
    arguments = parser.parse_args()
    manifest = load_manifest(arguments.manifest)
    checksum = str(manifest["sha256"])
    entries = manifest.get("entries", [])
    if not isinstance(entries, list):
        raise SystemExit("对象快照清单 entries 必须是数组")
    if arguments.apply:
        if arguments.confirmation != checksum:
            raise SystemExit("实际恢复必须通过 --confirmation 精确确认对象清单 SHA-256")
        settings = load_settings()
        client = _client(settings)
        for entry in entries:
            if not isinstance(entry, dict):
                raise SystemExit("对象快照清单包含无效条目")
            client.copy_object(
                Bucket=str(entry["source_bucket"]),
                Key=str(entry["source_key"]),
                CopySource={"Bucket": str(entry["backup_bucket"]), "Key": str(entry["backup_key"])},
                MetadataDirective="COPY",
            )
    print(
        json.dumps(
            {
                "mode": "applied" if arguments.apply else "verified_only",
                "manifest": str(arguments.manifest.resolve()),
                "sha256": checksum,
                "object_count": len(entries),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
