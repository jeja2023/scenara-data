"""为 Core/Model 本地联调生成与 Data 服务一致的签名身份上下文。"""

from __future__ import annotations

import argparse
import json
import os
import time
from uuid import uuid4

from scenara_data.api.security import sign_request_context


def _csv(value: str) -> tuple[str, ...]:
    return tuple(sorted({item.strip() for item in value.split(",") if item.strip()}))


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 X-Scenara-Context-* 签名请求头")
    parser.add_argument("--method", default="GET")
    parser.add_argument("--path", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--principal-type", choices=("user", "service_account"), default="service_account")
    parser.add_argument("--scopes", required=True, help="逗号分隔的权限范围")
    parser.add_argument("--entitlements", default="scenara.data")
    parser.add_argument("--request-id", default=None)
    parser.add_argument("--trace-id", default=None)
    parser.add_argument("--timestamp", type=int, default=None)
    parser.add_argument("--signing-key", default=os.getenv("SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY"))
    arguments = parser.parse_args()
    if not arguments.signing_key:
        raise SystemExit("必须通过 --signing-key 或 SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY 提供签名密钥")

    timestamp = arguments.timestamp or int(time.time())
    request_id = arguments.request_id or f"ctx-{uuid4().hex}"
    trace_id = arguments.trace_id or uuid4().hex
    scopes = _csv(arguments.scopes)
    entitlements = _csv(arguments.entitlements)
    signature = sign_request_context(
        arguments.signing_key,
        method=arguments.method,
        path=arguments.path,
        tenant_id=arguments.tenant_id,
        project_id=arguments.project_id,
        principal_id=arguments.principal_id,
        principal_type=arguments.principal_type,
        scopes=scopes,
        entitlements=entitlements,
        request_id=request_id,
        trace_id=trace_id,
        timestamp=timestamp,
    )
    print(
        json.dumps(
            {
                "Authorization": "Bearer <SCENARA_DATA_TRUSTED_SERVICE_TOKEN>",
                "X-Scenara-Tenant-Id": arguments.tenant_id,
                "X-Scenara-Project-Id": arguments.project_id,
                "X-Scenara-Principal-Id": arguments.principal_id,
                "X-Scenara-Principal-Type": arguments.principal_type,
                "X-Scenara-Permission-Scopes": ",".join(scopes),
                "X-Scenara-Product-Entitlements": ",".join(entitlements),
                "X-Request-Id": request_id,
                "X-Trace-Id": trace_id,
                "X-Scenara-Context-Timestamp": str(timestamp),
                "X-Scenara-Context-Signature": signature,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
