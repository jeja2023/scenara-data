"""本地数据工作台登录入口。

正式身份、用户目录和权限事实仍由 Core 平台负责；这里仅为本仓库独立前端提供本地开发和
直连部署可用的用户名密码会话。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request

from scenara_data.api.schemas import LoginRequest, LoginResponse, LoginSessionInfo
from scenara_data.api.security import issue_console_session, verify_console_login

router = APIRouter(tags=["认证"])


class LoginAttemptLimiter:
    """进程内登录限流；生产网关仍必须提供跨副本的统一限流。"""

    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts[key]
            while attempts and now - attempts[0] >= self._window_seconds:
                attempts.popleft()
            return len(attempts) < self._max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


def _limiter(request: Request) -> LoginAttemptLimiter:
    limiter = getattr(request.app.state, "login_attempt_limiter", None)
    if limiter is None:
        settings = request.app.state.settings
        limiter = LoginAttemptLimiter(
            max_attempts=settings.console_login_max_attempts,
            window_seconds=settings.console_login_window_seconds,
        )
        request.app.state.login_attempt_limiter = limiter
    return limiter


@router.post("/api/v1/auth/login", response_model=LoginResponse, summary="scenara data 登录")
@router.post("/internal/v1/auth/login", response_model=LoginResponse, include_in_schema=False)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    settings = request.app.state.settings
    if not settings.console_login_enabled:
        raise HTTPException(status_code=404)
    username = body.username.strip()
    source = request.client.host if request.client else "unknown"
    key = f"{source}:{username}"
    limiter = _limiter(request)
    if not limiter.allow(key):
        raise HTTPException(status_code=429)
    try:
        verify_console_login(settings, username, body.password)
    except Exception:
        limiter.record_failure(key)
        raise
    limiter.clear(key)
    session = issue_console_session(settings, username)
    return LoginResponse(
        token=session.token,
        username=session.username,
        expires_at=session.expires_at,
        session=LoginSessionInfo(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            project_id=session.project_id,
            user_id=session.username,
            principal_type="user",
            permission_scopes=session.permission_scopes,
            product_entitlements=session.product_entitlements,
            issued_at=session.issued_at,
            expires_at=session.expires_at,
        ),
    )
