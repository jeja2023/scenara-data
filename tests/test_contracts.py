from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_repository_contracts.py"
CONTRACTS_ROOT = ROOT.parent / "scenara-contracts"


def test_repository_contracts_validate_against_published_release() -> None:
    if not CONTRACTS_ROOT.is_dir():
        return
    subprocess.run(
        [sys.executable, str(SCRIPT), "--contracts-root", str(CONTRACTS_ROOT)],
        cwd=ROOT,
        check=True,
    )
