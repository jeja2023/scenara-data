from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scenara_data.api.schemas import DatasetVersionReference, HardSampleContractManifest  # noqa: E402
from scenara_data.contracts import (  # noqa: E402
    CONTRACT_MANIFEST_SHA256,
    CONTRACT_VERSION,
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema(path: Path) -> Draft202012Validator:
    document = _json(path)
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


def _require(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"缺少契约制品：{path}")
    return path


def _contracts_root(path: Path | None) -> Path:
    if path is not None:
        return path.resolve()
    sibling = ROOT.parent / "scenara-contracts"
    if sibling.is_dir():
        return sibling.resolve()
    env = Path.cwd() / "scenara-contracts"
    if env.is_dir():
        return env.resolve()
    raise SystemExit("未找到仓库契约检出目录，请传入 --contracts-root")


def validate(contracts_root: Path) -> None:
    manifest = contracts_root / "contracts" / "repository" / f"v{CONTRACT_VERSION}" / "manifest.json"
    release_manifest = _require(manifest)
    digest = sha256(release_manifest.read_bytes()).hexdigest()
    if digest != CONTRACT_MANIFEST_SHA256:
        raise SystemExit(
            "已发布仓库契约清单的摘要不匹配："
            f"预期 {CONTRACT_MANIFEST_SHA256}，实际 {digest}"
        )

    published = _json(release_manifest)
    contracts = {str(item["contract_id"]): item for item in published.get("contracts", [])}
    required = {"dataset-version-input", "hard-sample-handoff"}
    if not required.issubset(contracts):
        missing = ", ".join(sorted(required - set(contracts)))
        raise SystemExit(f"已发布仓库契约缺少必需条目：{missing}")

    for contract_id in sorted(required):
        entry = contracts[contract_id]
        schema_path = _require(contracts_root / str(entry["schema_path"]))
        example_path = _require(contracts_root / str(entry["example_path"]))
        if sha256(schema_path.read_bytes()).hexdigest() != str(entry["schema_sha256"]):
            raise SystemExit(f"{contract_id} 模式摘要与清单不一致")
        if sha256(example_path.read_bytes()).hexdigest() != str(entry["example_sha256"]):
            raise SystemExit(f"{contract_id} 示例摘要与清单不一致")
        validator = _schema(schema_path)
        example = _json(example_path)
        validator.validate(example)
        if contract_id == "dataset-version-input":
            DatasetVersionReference.model_validate(example)
        elif contract_id == "hard-sample-handoff":
            HardSampleContractManifest.model_validate(example)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    contracts_root = None
    if arguments:
        if len(arguments) != 2 or arguments[0] != "--contracts-root":
            raise SystemExit("用法：python scripts/validate_repository_contracts.py [--contracts-root PATH]")
        contracts_root = Path(arguments[1])
    validate(_contracts_root(contracts_root))
    print("仓库契约校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
