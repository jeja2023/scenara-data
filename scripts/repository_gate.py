from __future__ import annotations

import re
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
    problems = [f"missing required path: {path}" for path in REQUIRED_PATHS if not (ROOT / path).exists()]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "当前成熟度：`seed`" not in readme:
        problems.append("README must declare seed maturity")
    if "责任团队：Scenara Data" not in readme:
        problems.append("README must declare the responsible team")

    lock = yaml.safe_load((ROOT / "configs/contracts/repository-contracts.yml").read_text(encoding="utf-8"))
    if lock.get("version") != "1.0.0":
        problems.append("repository contract version must be pinned to 1.0.0")
    if lock.get("manifest_sha256") != "4b070ce7e8d11f6c21641559c844b736482fa38e726b0778eb2d9c2834feecd6":
        problems.append("repository contract manifest digest does not match the published release")

    forbidden = re.compile(r"\b(?:from|import)\s+(?:scenara|scenara_model)\b")
    for path in (ROOT / "src").rglob("*.py"):
        if forbidden.search(path.read_text(encoding="utf-8")):
            problems.append(f"forbidden cross-repository source import: {path.relative_to(ROOT)}")

    if problems:
        for problem in problems:
            print(problem)
        return 1
    print("repository gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
