from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend" / "data-console"
DEFAULT_BACKEND_PORT = 8081
DEFAULT_FRONTEND_PORT = 5173


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 Scenara Data 本地开发服务")
    parser.add_argument("--mode", choices=("all", "backend", "frontend"), default="all")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--api-base", default="http://127.0.0.1:8081")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--app", default="scenara_data.api.app:app")
    parser.add_argument("--strict-port", action="store_true", help="backend-only 模式下不自动寻找替代端口")
    parser.add_argument("--skip-frontend-install", action="store_true")
    return parser.parse_args(argv)


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _integration_settings() -> dict[str, str]:
    return {
        "database_url": os.getenv(
            "SCENARA_DATA_INTEGRATION_DATABASE_URL",
            "postgresql://scenara:123456@127.0.0.1:5433/scenara?options=-csearch_path%3Dscenara_data_integration_codex,public",
        ),
        "redis_url": os.getenv("SCENARA_DATA_INTEGRATION_REDIS_URL", "redis://127.0.0.1:6379/1"),
        "s3_endpoint": os.getenv("SCENARA_DATA_INTEGRATION_S3_ENDPOINT_URL", "http://127.0.0.1:9000"),
        "s3_access_key": os.getenv("SCENARA_DATA_INTEGRATION_S3_ACCESS_KEY_ID", "minioadmin"),
        "s3_secret_key": os.getenv("SCENARA_DATA_INTEGRATION_S3_SECRET_ACCESS_KEY", "minioadmin"),
        "s3_region": os.getenv("SCENARA_DATA_INTEGRATION_S3_REGION", "us-east-1"),
    }


def _check_postgres(database_url: str) -> str | None:
    try:
        psycopg = importlib.import_module("psycopg")
    except ImportError as exc:
        return f"PostgreSQL: 缺少 Python 依赖 psycopg ({exc})"
    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
        return None
    except Exception as exc:
        return f"PostgreSQL: {exc}"


def _check_redis(redis_url: str) -> str | None:
    try:
        redis = importlib.import_module("redis")
    except ImportError as exc:
        return f"Redis: 缺少 Python 依赖 redis ({exc})"
    try:
        client = redis.Redis.from_url(redis_url, protocol=2, socket_connect_timeout=3, socket_timeout=3)
        client.ping()
        return None
    except Exception as exc:
        return f"Redis: {exc}"


def _check_s3(endpoint: str, access_key: str, secret_key: str, region: str) -> str | None:
    try:
        boto3 = importlib.import_module("boto3")
        Config = importlib.import_module("botocore.config").Config
    except ImportError as exc:
        return f"MinIO/S3: 缺少 Python 依赖 boto3/botocore ({exc})"
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(s3={"addressing_style": "path"}, connect_timeout=3, read_timeout=3),
        )
        client.list_buckets()
        return None
    except Exception as exc:
        return f"MinIO/S3: {exc}"


def _validate_local_dependencies() -> None:
    settings = _integration_settings()
    problems: list[str] = []
    postgres = _check_postgres(settings["database_url"])
    if postgres is not None:
        problems.append(postgres)
    redis_error = _check_redis(settings["redis_url"])
    if redis_error is not None:
        problems.append(redis_error)
    s3_error = _check_s3(
        settings["s3_endpoint"],
        settings["s3_access_key"],
        settings["s3_secret_key"],
        settings["s3_region"],
    )
    if s3_error is not None:
        problems.append(s3_error)
    if problems:
        message = "\n".join(f"- {item}" for item in problems)
        raise SystemExit("本机依赖检查失败:\n" + message)


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _choose_port(host: str, preferred_port: int, *, scan_limit: int = 25) -> int:
    for candidate in range(preferred_port, preferred_port + scan_limit):
        if _port_available(host, candidate):
            return candidate
    raise SystemExit(f"未能在 {preferred_port} 到 {preferred_port + scan_limit - 1} 之间找到可用端口")


def _probe_http(url: str, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= getattr(response, "status", 200) < 500:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise SystemExit(f"等待服务就绪超时：{url}；最后错误：{last_error}")


def _ensure_frontend_dependencies() -> None:
    if (FRONTEND_DIR / "node_modules").exists():
        return
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("未找到 npm，请先安装 Node.js 与 npm")
    print("前端依赖缺失，正在安装 npm packages...")
    subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR, check=True)


def _run_backend(args: argparse.Namespace, *, strict_port: bool = False) -> int:
    try:
        uvicorn = importlib.import_module("uvicorn")
    except ImportError as exc:
        raise SystemExit(f"缺少 Python 依赖 uvicorn：{exc}") from exc
    _load_env_file((ROOT / args.env_file).resolve())
    os.environ.setdefault("SCENARA_DATA_CORE_EVENT_ENDPOINT", "http://127.0.0.1:18080/internal/v1/data/events")
    os.environ.setdefault("SCENARA_DATA_CORE_EVENT_TOKEN", "scenara-data-dev-event-token")
    _validate_local_dependencies()
    port = args.backend_port if strict_port else _choose_port(args.host, args.backend_port)
    if port != args.backend_port:
        print(f"后端端口 {args.backend_port} 已被占用，自动切换到 {port}")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(
        args.app,
        host=args.host,
        port=port,
        reload=args.reload,
        env_file=None,
        loop="auto" if sys.platform != "win32" else "asyncio",
        factory=False,
    )
    return 0


def _start_frontend(backend_port: int, frontend_port: int, *, skip_install: bool = False) -> subprocess.Popen[object]:
    if not skip_install:
        _ensure_frontend_dependencies()
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("未找到 npm，请先安装 Node.js 与 npm")
    env = os.environ.copy()
    env.setdefault("VITE_DATA_API_BASE", f"http://127.0.0.1:{backend_port}")
    command = [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port)]
    return subprocess.Popen(command, cwd=FRONTEND_DIR, env=env)


def _terminate_process(process: subprocess.Popen[object], name: str) -> None:
    if process.poll() is not None:
        return
    print(f"正在停止 {name}...")
    try:
        process.terminate()
        process.wait(timeout=10)
    except Exception:
        process.kill()


def _run_all(args: argparse.Namespace) -> int:
    backend_port = _choose_port(args.host, args.backend_port)
    frontend_port = _choose_port(args.host, args.frontend_port)

    backend_env = os.environ.copy()
    backend_env["SCENARA_DATA_CORS_ALLOW_ORIGINS"] = ",".join(
        [f"http://127.0.0.1:{frontend_port}", f"http://localhost:{frontend_port}"]
    )

    backend_cmd = [
        sys.executable,
        str(ROOT / "start.py"),
        "--mode",
        "backend",
        "--host",
        args.host,
        "--backend-port",
        str(backend_port),
        "--env-file",
        args.env_file,
        "--strict-port",
    ]
    if args.reload:
        backend_cmd.append("--reload")
    if args.app != "scenara_data.api.app:app":
        backend_cmd.extend(["--app", args.app])

    backend_proc = subprocess.Popen(backend_cmd, cwd=ROOT, env=backend_env)
    frontend_proc: subprocess.Popen[object] | None = None
    try:
        _probe_http(f"http://127.0.0.1:{backend_port}/health")
        frontend_proc = _start_frontend(backend_port, frontend_port, skip_install=args.skip_frontend_install)
        print(f"后端已启动：http://127.0.0.1:{backend_port}")
        print(f"前端已启动：http://127.0.0.1:{frontend_port}")
        while True:
            backend_code = backend_proc.poll()
            frontend_code = frontend_proc.poll() if frontend_proc is not None else None
            if backend_code is not None:
                if backend_code != 0:
                    raise SystemExit(f"后端进程退出，代码 {backend_code}")
            if frontend_code is not None:
                if frontend_code != 0:
                    raise SystemExit(f"前端进程退出，代码 {frontend_code}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if frontend_proc is not None:
            _terminate_process(frontend_proc, "前端")
        _terminate_process(backend_proc, "后端")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.mode == "backend":
        return _run_backend(args, strict_port=args.strict_port)
    if args.mode == "frontend":
        backend_port = _choose_port(args.host, args.backend_port)
        frontend_port = _choose_port(args.host, args.frontend_port)
        print(f"将使用后端地址：http://127.0.0.1:{backend_port}")
        proc = _start_frontend(backend_port, frontend_port, skip_install=args.skip_frontend_install)
        print(f"前端已启动：http://127.0.0.1:{frontend_port}")
        try:
            proc.wait()
            return int(proc.returncode or 0)
        except KeyboardInterrupt:
            _terminate_process(proc, "前端")
            return 0
    return _run_all(args)


if __name__ == "__main__":
    raise SystemExit(main())
