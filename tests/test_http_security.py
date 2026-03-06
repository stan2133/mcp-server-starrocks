import os
import time
from unittest.mock import patch

import jwt
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.mcp_server_starrocks.http_security import (
    AuthAndIPMiddleware,
    JWTValidator,
    SecurityConfig,
)


def make_token(secret: str, scope: str = "") -> str:
    now = int(time.time())
    payload = {
        "sub": "test-user",
        "iat": now,
        "exp": now + 3600,
    }
    if scope:
        payload["scope"] = scope
    return jwt.encode(payload, secret, algorithm="HS256")


async def ok_endpoint(_request):
    return JSONResponse({"ok": True})


class TestSecurityConfig:
    def test_default_config_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = SecurityConfig.from_env()
            assert cfg.enabled is False
            assert cfg.sso_enabled is False
            assert cfg.ip_filter_enabled is False

    def test_parse_ip_allowlist(self):
        with patch.dict(os.environ, {"MCP_IP_ALLOWLIST": "127.0.0.1,10.0.0.0/8"}, clear=True):
            cfg = SecurityConfig.from_env()
            assert cfg.ip_filter_enabled is True
            assert len(cfg.ip_allowlist) == 2

    def test_invalid_ip_allowlist(self):
        with patch.dict(os.environ, {"MCP_IP_ALLOWLIST": "not-an-ip"}, clear=True):
            with pytest.raises(ValueError, match="Invalid MCP_IP_ALLOWLIST entry"):
                SecurityConfig.from_env()

    def test_sso_enabled_requires_jwks_or_secret(self):
        with patch.dict(os.environ, {"MCP_SSO_ENABLED": "true"}, clear=True):
            with pytest.raises(ValueError, match="neither MCP_SSO_JWKS_URL nor MCP_SSO_JWT_SECRET"):
                SecurityConfig.from_env()


class TestJWTValidator:
    def test_hs256_decode_and_scope_extract(self):
        cfg = SecurityConfig(
            sso_enabled=True,
            sso_jwt_secret="secret",
            sso_jwt_algorithms=["HS256"],
        )
        validator = JWTValidator(cfg)
        token = make_token("secret", scope="mcp.read mcp.write")
        claims = validator.decode_token(token)
        scopes = JWTValidator.extract_scopes(claims)
        assert "mcp.read" in scopes
        assert "mcp.write" in scopes


class TestAuthAndIPMiddleware:
    def _make_app(self, config: SecurityConfig) -> TestClient:
        app = Starlette(
            routes=[Route("/mcp", ok_endpoint, methods=["GET", "OPTIONS"])],
            middleware=[Middleware(AuthAndIPMiddleware, config=config)],
        )
        return TestClient(app)

    def test_enforce_sso(self):
        config = SecurityConfig(
            sso_enabled=True,
            sso_jwt_secret="secret",
            sso_jwt_algorithms=["HS256"],
            sso_required_scopes={"mcp.access"},
        )
        client = self._make_app(config)

        # Missing token.
        resp = client.get("/mcp")
        assert resp.status_code == 401

        # Token exists but scope is missing.
        token_without_scope = make_token("secret", scope="mcp.read")
        resp = client.get("/mcp", headers={"Authorization": f"Bearer {token_without_scope}"})
        assert resp.status_code == 401

        # Valid token and scope.
        token = make_token("secret", scope="mcp.access mcp.read")
        resp = client.get("/mcp", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_enforce_ip_allowlist(self):
        # Allow only 10.0.0.0/8.
        with patch.dict(
            os.environ,
            {"MCP_IP_ALLOWLIST": "10.0.0.0/8", "MCP_TRUST_PROXY_HEADERS": "true"},
            clear=True,
        ):
            config = SecurityConfig.from_env()

        client = self._make_app(config)
        denied = client.get("/mcp", headers={"X-Forwarded-For": "203.0.113.10"})
        assert denied.status_code == 403

        allowed = client.get("/mcp", headers={"X-Forwarded-For": "10.1.2.3"})
        assert allowed.status_code == 200

    def test_options_is_bypassed(self):
        config = SecurityConfig(
            sso_enabled=True,
            sso_jwt_secret="secret",
            sso_jwt_algorithms=["HS256"],
            ip_allowlist=[],
        )
        client = self._make_app(config)
        resp = client.options("/mcp")
        assert resp.status_code == 200
