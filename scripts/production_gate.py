"""生产编排的静态门禁：阻止开发 Compose 和未加固运行配置误入发布流程。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    production = (ROOT / "deploy" / "compose.production.yml").read_text(encoding="utf-8")
    development = (ROOT / "deploy" / "compose.yml").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    migration = ROOT / "migrations" / "0003_production_integrity.sql"

    problems: list[str] = []
    required_production = (
        "SCENARA_DATA_IMAGE:?必须设置 SCENARA_DATA_IMAGE",
        "@sha256:",
        "SCENARA_DATA_DEPLOYMENT_PROFILE: production",
        "SCENARA_DATA_DATABASE_URL_FILE",
        "SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY_FILE",
        "SCENARA_DATA_CONSOLE_LOGIN_ENABLED: \"false\"",
        "read_only: true",
        "cap_drop: [\"ALL\"]",
        "no-new-privileges:true",
        "external: true",
    )
    for item in required_production:
        if item not in production:
            problems.append(f"生产编排缺少安全约束：{item}")
    if "ports:" in production:
        problems.append("生产编排不得把 API 或基础设施端口直接暴露到宿主机")
    if ":latest" in development:
        problems.append("开发编排不得使用浮动 latest 镜像")
    for line in development.splitlines():
        stripped = line.strip()
        if stripped.startswith("image:") and "@sha256:" not in stripped:
            problems.append(f"开发编排镜像必须固定 digest：{stripped}")
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    if not dockerfile.startswith("FROM python@sha256:"):
        problems.append("Dockerfile 基础镜像必须固定 digest")
    if ".env" not in dockerignore:
        problems.append(".dockerignore 必须排除 .env 密钥文件")
    if not migration.is_file():
        problems.append("缺少生产完整性修复迁移 0003")
    required_operations = (
        "backup_postgres.py",
        "backup_object_store.py",
        "restore_postgres.py",
        "restore_object_store.py",
        "verify_object_inventory.py",
        "rebuild_outbox.py",
        "load_test_api.py",
        "preproduction_check.py",
        "sign_context.py",
    )
    for name in required_operations:
        if not (ROOT / "scripts" / name).is_file():
            problems.append(f"缺少上线前运维工具：scripts/{name}")

    if problems:
        print("\n".join(problems))
        return 1
    print("生产编排静态门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
