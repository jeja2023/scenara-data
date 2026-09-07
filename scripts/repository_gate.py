from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "README.md",
    "CHANGELOG.md",
    "src/scenara_data/domain/models.py",
    "src/scenara_data/ports/interfaces.py",
    "tests",
    "docs/ARCHITECTURE.md",
    "docs/API.md",
    "docs/DATA_MODEL.md",
    "docs/DEPLOYMENT.md",
    "docs/TESTING.md",
    "docs/MIGRATION.md",
    "docs/IAM_AND_AUDIT.md",
    "docs/OPERATIONS.md",
    "docs/SECURITY.md",
    "configs/contracts/repository-contracts.yml",
    "configs/permissions/data-permissions.yml",
    "deploy",
)


def main() -> int:
    problems = [f"缺少必需路径：{path}" for path in REQUIRED_PATHS if not (ROOT / path).exists()]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    config = (ROOT / "src/scenara_data/config.py").read_text(encoding="utf-8")
    declared = re.search(r'DECLARED_MATURITY\s*=\s*"([a-z_]+)"', config)
    maturity = declared.group(1) if declared else None
    if maturity not in {"seed", "implemented", "qualified", "production_ready"}:
        problems.append("配置必须声明已登记的成熟度")
    if maturity == "production_ready":
        problems.append("缺少环境证据时，仓库门禁不能批准生产就绪状态")
    if maturity is not None and f"当前成熟度：`{maturity}`" not in readme:
        problems.append("README 中的成熟度与配置项 DECLARED_MATURITY 不一致")
    if "责任团队：scenara data" not in readme:
        problems.append("README 必须声明责任团队")

    lock = yaml.safe_load((ROOT / "configs/contracts/repository-contracts.yml").read_text(encoding="utf-8"))
    if lock.get("version") != "1.2.0":
        problems.append("仓库契约版本必须固定为 1.2.0")
    if lock.get("manifest_sha256") != "2889523368f6a4d2297b66fc714dfe38d882add7484605c12dcfa3e2e451d111":
        problems.append("仓库契约清单摘要与已发布版本不一致")
    if lock.get("domain_annotation_release") != "1.1.0":
        problems.append("领域标注模式版本必须固定为 1.1.0")
    if lock.get("domain_annotation_manifest_sha256") != "0f2a7ffb271320d5be45a92bf9fc63b08656c33c1983ee01413d7131ed4ba278":
        problems.append("领域标注模式清单摘要与已发布版本不一致")

    contracts_root = ROOT / "scenara-contracts"
    if not contracts_root.is_dir():
        contracts_root = ROOT.parent / "scenara-contracts"
    if contracts_root.is_dir():
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_repository_contracts.py"),
                "--contracts-root",
                str(contracts_root),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip() or "仓库契约校验失败"
            problems.append(detail)

    forbidden = re.compile(r"\b(?:from|import)\s+(?:scenara|scenara_model)\b")
    for path in (ROOT / "src").rglob("*.py"):
        if forbidden.search(path.read_text(encoding="utf-8")):
            problems.append(f"禁止跨仓库导入源代码：{path.relative_to(ROOT)}")

    if problems:
        for problem in problems:
            print(problem)
        return 1
    print("仓库门禁检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
