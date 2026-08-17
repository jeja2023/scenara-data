"""本地数据工作台登录入口。

正式身份、用户目录和权限事实仍由 Core 平台负责；这里仅为本仓库独立前端提供本地开发和
直连部署可用的用户名密码会话。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from scenara_data.api.schemas import LoginRequest, LoginResponse, LoginSessionInfo
from scenara_data.api.security import issue_console_session, verify_console_login

router = APIRouter(tags=["认证"])


@router.post("/api/v1/auth/login", response_model=LoginResponse, summary="数据工作台登录")
@router.post("/internal/v1/auth/login", response_model=LoginResponse, include_in_schema=False)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    settings = request.app.state.settings
    username = body.username.strip()
    verify_console_login(settings, username, body.password)
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
