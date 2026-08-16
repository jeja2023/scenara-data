from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from scenara_data.adapters.migration_package import FilesystemMigrationPackage
from scenara_data.api.container import build_container
from scenara_data.config import load_settings
from scenara_data.ports.interfaces import RequestContext


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a checksummed Scenara Core migration package")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", default="data-migration-service")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    container = build_container(load_settings())
    context = RequestContext(
        tenant_id=args.tenant_id,
        project_id=args.project_id,
        principal_id=args.principal_id,
        principal_type="service_account",
        permission_scopes=("data.import.execute", "data.dataset.read"),
        product_entitlements=("scenara.data",),
        request_id=f"migration-{secrets.token_hex(12)}",
        trace_id=secrets.token_hex(16),
    )
    report = container.migrations.import_package(
        FilesystemMigrationPackage(args.package), context, dry_run=args.dry_run
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    return 0 if str(report.status) == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
