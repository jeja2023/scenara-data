"""验证 PostgreSQL 备份并在显式确认后恢复到指定目标数据库。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

try:  # 支持 `python scripts/restore_postgres.py` 与测试中的模块导入。
    from scripts.backup_postgres import sha256_file
except ModuleNotFoundError:  # pragma: no cover - 仅直接脚本执行路径
    from backup_postgres import sha256_file


def load_and_verify_manifest(artifact: Path, manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = str(manifest.get("artifact", {}).get("sha256", ""))
    actual = sha256_file(artifact)
    if len(recorded) != 64 or actual != recorded:
        raise ValueError("备份文件 SHA-256 与清单不一致")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="恢复 PostgreSQL 自定义格式备份")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target-database-url", required=True)
    parser.add_argument("--pg-restore", default="pg_restore")
    parser.add_argument("--apply", action="store_true", help="实际恢复；默认仅校验")
    parser.add_argument("--confirmation", default="", help="实际恢复时必须填写备份 SHA-256")
    arguments = parser.parse_args()
    manifest = load_and_verify_manifest(arguments.artifact, arguments.manifest)
    checksum = str(manifest["artifact"]["sha256"])
    if arguments.apply:
        if arguments.confirmation != checksum:
            raise SystemExit("实际恢复必须通过 --confirmation 精确确认备份 SHA-256")
        subprocess.run(
            [
                arguments.pg_restore,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                arguments.target_database_url,
                str(arguments.artifact),
            ],
            check=True,
        )
    print(
        json.dumps(
            {
                "mode": "applied" if arguments.apply else "verified_only",
                "artifact": str(arguments.artifact.resolve()),
                "sha256": checksum,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
