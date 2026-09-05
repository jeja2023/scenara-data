"""对只读数据 API 执行受控并发压测，并输出可归档的延迟/错误率报告。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from uuid import uuid4

import httpx

from scenara_data.api.security import sign_request_context


@dataclass(frozen=True, slots=True)
class LoadReport:
    schema_version: str
    base_url: str
    path: str
    request_count: int
    concurrency: int
    successful_count: int
    failed_count: int
    elapsed_seconds: float
    requests_per_second: float
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    mean_ms: float | None
    status_codes: dict[str, int]


def percentile(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * proportion)))
    return round(ordered[index], 3)


def _csv(value: str) -> tuple[str, ...]:
    return tuple(sorted({item.strip() for item in value.split(",") if item.strip()}))


def request_headers(arguments: argparse.Namespace) -> dict[str, str]:
    trace_id = uuid4().hex
    request_id = f"load-{uuid4().hex}"
    scopes = _csv(arguments.scopes)
    entitlements = _csv(arguments.entitlements)
    headers = {
        "Authorization": f"Bearer {arguments.token}",
        "Accept": "application/json",
        "X-Scenara-Tenant-Id": arguments.tenant_id,
        "X-Scenara-Project-Id": arguments.project_id,
        "X-Scenara-Principal-Id": arguments.principal_id,
        "X-Scenara-Principal-Type": arguments.principal_type,
        "X-Scenara-Permission-Scopes": ",".join(scopes),
        "X-Scenara-Product-Entitlements": ",".join(entitlements),
        "X-Request-Id": request_id,
        "X-Trace-Id": trace_id,
    }
    if arguments.context_signing_key:
        timestamp = int(time.time())
        headers["X-Scenara-Context-Timestamp"] = str(timestamp)
        headers["X-Scenara-Context-Signature"] = sign_request_context(
            arguments.context_signing_key,
            method="GET",
            path=arguments.path.split("?", 1)[0],
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
    return headers


async def run_load(arguments: argparse.Namespace) -> LoadReport:
    durations: list[float] = []
    status_codes: dict[str, int] = {}
    counter = 0
    lock = asyncio.Lock()

    async def worker(client: httpx.AsyncClient) -> None:
        nonlocal counter
        while True:
            async with lock:
                if counter >= arguments.requests:
                    return
                counter += 1
            started = time.perf_counter()
            try:
                response = await client.get(arguments.path, headers=request_headers(arguments))
                code = str(response.status_code)
            except httpx.HTTPError:
                code = "network_error"
            elapsed = (time.perf_counter() - started) * 1000
            async with lock:
                durations.append(elapsed)
                status_codes[code] = status_codes.get(code, 0) + 1

    started = time.perf_counter()
    timeout = httpx.Timeout(arguments.timeout_seconds)
    async with httpx.AsyncClient(base_url=arguments.base_url.rstrip("/"), timeout=timeout) as client:
        await asyncio.gather(*(worker(client) for _ in range(arguments.concurrency)))
    elapsed_seconds = time.perf_counter() - started
    successful = sum(count for code, count in status_codes.items() if code.startswith("2"))
    failed = arguments.requests - successful
    return LoadReport(
        schema_version="1.0",
        base_url=arguments.base_url,
        path=arguments.path,
        request_count=arguments.requests,
        concurrency=arguments.concurrency,
        successful_count=successful,
        failed_count=failed,
        elapsed_seconds=round(elapsed_seconds, 3),
        requests_per_second=round(arguments.requests / elapsed_seconds, 3) if elapsed_seconds else 0.0,
        p50_ms=percentile(durations, 0.50),
        p95_ms=percentile(durations, 0.95),
        p99_ms=percentile(durations, 0.99),
        mean_ms=round(mean(durations), 3) if durations else None,
        status_codes=dict(sorted(status_codes.items())),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="对只读 Data API 执行并发负载测试")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", default="/internal/v1/datasets?limit=1")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--token", default=os.getenv("SCENARA_DATA_TRUSTED_SERVICE_TOKEN"))
    parser.add_argument("--context-signing-key", default=os.getenv("SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY"))
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", default="load-test-service")
    parser.add_argument("--principal-type", choices=("user", "service_account"), default="service_account")
    parser.add_argument("--scopes", default="data.dataset.read")
    parser.add_argument("--entitlements", default="scenara.data")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    arguments = parser.parse_args()
    if not arguments.token:
        raise SystemExit("必须提供 --token 或 SCENARA_DATA_TRUSTED_SERVICE_TOKEN")
    if arguments.requests <= 0 or arguments.concurrency <= 0 or arguments.timeout_seconds <= 0:
        raise SystemExit("requests、concurrency 和 timeout-seconds 必须为正数")
    report = asyncio.run(run_load(arguments))
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0 if report.failed_count / report.request_count <= arguments.max_error_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
