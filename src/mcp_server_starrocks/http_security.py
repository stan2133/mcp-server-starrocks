# Copyright 2021-present StarRocks, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass, field
import ipaddress
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set, Union
import urllib.error
import urllib.request

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

try:
    import jwt
    from jwt import InvalidTokenError, PyJWKClient
except ImportError:  # pragma: no cover
    jwt = None
    InvalidTokenError = Exception
    PyJWKClient = None


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


IPAddressNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def _parse_positive_int(value: Optional[str], default: int, env_name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer, got '{value}'") from exc
    if parsed <= 0:
        raise ValueError(f"{env_name} must be greater than 0, got {parsed}")
    return parsed


def _parse_positive_float(value: Optional[str], default: float, env_name: str) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be a number, got '{value}'") from exc
    if parsed <= 0:
        raise ValueError(f"{env_name} must be greater than 0, got {parsed}")
    return parsed


def _parse_allowlist_entries(entries: List[str]) -> List[IPAddressNetwork]:
    networks: List[IPAddressNetwork] = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                ip_obj = ipaddress.ip_address(entry)
                prefix = 32 if ip_obj.version == 4 else 128
                networks.append(ipaddress.ip_network(f"{entry}/{prefix}", strict=False))
        except ValueError as exc:
            raise ValueError(f"Invalid MCP_IP_ALLOWLIST entry '{entry}': {exc}") from exc
    return networks


def _parse_allowlist(value: Optional[str]) -> List[IPAddressNetwork]:
    return _parse_allowlist_entries(_parse_csv(value))


def _split_plain_text_allowlist_entries(content: str) -> List[str]:
    entries: List[str] = []
    for line in content.splitlines():
        parts = [part.strip() for part in line.split(",") if part.strip()]
        entries.extend(parts)
    return entries


def _extract_allowlist_from_json(payload: Any) -> List[str]:
    if isinstance(payload, str):
        return _split_plain_text_allowlist_entries(payload)

    if isinstance(payload, list):
        entries: List[str] = []
        for item in payload:
            if isinstance(item, str):
                if item.strip():
                    entries.append(item.strip())
            elif isinstance(item, dict):
                for key in ("cidr", "ip", "value"):
                    value = item.get(key)
                    if value:
                        entries.append(str(value).strip())
                        break
            elif item is not None:
                entries.append(str(item).strip())
        return [item for item in entries if item]

    if isinstance(payload, dict):
        for key in ("allowlist", "ip_allowlist", "ips", "cidrs", "entries", "data"):
            if key in payload:
                return _extract_allowlist_from_json(payload[key])
        if "cidr" in payload:
            return [str(payload["cidr"]).strip()]
        if "ip" in payload:
            return [str(payload["ip"]).strip()]

    raise ValueError("Unsupported HTTP allowlist response format")


def _parse_allowlist_http_payload(content: str, content_type: Optional[str]) -> List[IPAddressNetwork]:
    body = content.strip()
    if not body:
        return []

    lower_content_type = (content_type or "").lower()
    should_try_json = (
        "json" in lower_content_type or body.startswith("{") or body.startswith("[")
    )

    entries: List[str]
    if should_try_json:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON allowlist payload: {exc}") from exc
        entries = _extract_allowlist_from_json(payload)
    else:
        entries = _split_plain_text_allowlist_entries(body)

    return _parse_allowlist_entries(entries)


@dataclass
class SecurityConfig:
    sso_enabled: bool = False
    sso_jwks_url: Optional[str] = None
    sso_jwt_secret: Optional[str] = None
    sso_jwt_algorithms: List[str] = field(default_factory=list)
    sso_issuer: Optional[str] = None
    sso_audience: Optional[str] = None
    sso_required_scopes: Set[str] = field(default_factory=set)
    ip_allowlist: List[IPAddressNetwork] = field(default_factory=list)
    ip_allowlist_url: Optional[str] = None
    ip_allowlist_refresh_seconds: int = 60
    ip_allowlist_http_timeout_seconds: float = 3.0
    ip_allowlist_fail_open: bool = False
    ip_allowlist_bearer_token: Optional[str] = None
    trust_proxy_headers: bool = False

    @property
    def ip_filter_enabled(self) -> bool:
        return len(self.ip_allowlist) > 0 or bool(self.ip_allowlist_url)

    @property
    def enabled(self) -> bool:
        return self.sso_enabled or self.ip_filter_enabled

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        sso_enabled = _parse_bool(os.getenv("MCP_SSO_ENABLED"), False)
        sso_jwks_url = os.getenv("MCP_SSO_JWKS_URL")
        sso_jwt_secret = os.getenv("MCP_SSO_JWT_SECRET")
        sso_issuer = os.getenv("MCP_SSO_ISSUER")
        sso_audience = os.getenv("MCP_SSO_AUDIENCE")
        trust_proxy_headers = _parse_bool(os.getenv("MCP_TRUST_PROXY_HEADERS"), False)

        algs = _parse_csv(os.getenv("MCP_SSO_JWT_ALGORITHMS"))
        required_scopes = set(_parse_csv(os.getenv("MCP_SSO_REQUIRED_SCOPES")))
        ip_allowlist = _parse_allowlist(os.getenv("MCP_IP_ALLOWLIST"))
        ip_allowlist_url = os.getenv("MCP_IP_ALLOWLIST_URL")
        ip_allowlist_refresh_seconds = _parse_positive_int(
            os.getenv("MCP_IP_ALLOWLIST_REFRESH_SECONDS"),
            default=60,
            env_name="MCP_IP_ALLOWLIST_REFRESH_SECONDS",
        )
        ip_allowlist_http_timeout_seconds = _parse_positive_float(
            os.getenv("MCP_IP_ALLOWLIST_HTTP_TIMEOUT_SECONDS"),
            default=3.0,
            env_name="MCP_IP_ALLOWLIST_HTTP_TIMEOUT_SECONDS",
        )
        ip_allowlist_fail_open = _parse_bool(os.getenv("MCP_IP_ALLOWLIST_FAIL_OPEN"), False)
        ip_allowlist_bearer_token = os.getenv("MCP_IP_ALLOWLIST_BEARER_TOKEN")

        if sso_enabled:
            if jwt is None:
                raise ValueError("MCP_SSO_ENABLED=true requires PyJWT to be installed")
            if not sso_jwks_url and not sso_jwt_secret:
                raise ValueError("SSO is enabled but neither MCP_SSO_JWKS_URL nor MCP_SSO_JWT_SECRET is configured")
            if not algs:
                algs = ["RS256"] if sso_jwks_url else ["HS256"]
        else:
            algs = algs or []

        return cls(
            sso_enabled=sso_enabled,
            sso_jwks_url=sso_jwks_url,
            sso_jwt_secret=sso_jwt_secret,
            sso_jwt_algorithms=algs,
            sso_issuer=sso_issuer,
            sso_audience=sso_audience,
            sso_required_scopes=required_scopes,
            ip_allowlist=ip_allowlist,
            ip_allowlist_url=ip_allowlist_url,
            ip_allowlist_refresh_seconds=ip_allowlist_refresh_seconds,
            ip_allowlist_http_timeout_seconds=ip_allowlist_http_timeout_seconds,
            ip_allowlist_fail_open=ip_allowlist_fail_open,
            ip_allowlist_bearer_token=ip_allowlist_bearer_token,
            trust_proxy_headers=trust_proxy_headers,
        )


class IPAllowlistProvider:
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._lock = threading.Lock()
        self._allowlist: List[IPAddressNetwork] = list(config.ip_allowlist)
        self._last_refresh_attempt: float = 0.0
        self._last_refresh_success: float = 0.0
        self._last_error: Optional[str] = None

        if self.config.ip_allowlist_url:
            # On startup: fail fast when no local fallback and fail-open is disabled.
            fail_hard = not self._allowlist and not self.config.ip_allowlist_fail_open
            self._refresh_allowlist(fail_hard=fail_hard)

    def get_allowlist(self) -> List[IPAddressNetwork]:
        if not self.config.ip_allowlist_url:
            return self._allowlist

        now = time.time()
        refresh_interval = self.config.ip_allowlist_refresh_seconds
        if now - self._last_refresh_attempt < refresh_interval:
            return self._allowlist

        with self._lock:
            now = time.time()
            if now - self._last_refresh_attempt < refresh_interval:
                return self._allowlist
            self._refresh_allowlist(fail_hard=False)
            return self._allowlist

    def _refresh_allowlist(self, fail_hard: bool) -> None:
        self._last_refresh_attempt = time.time()
        try:
            allowlist = self._fetch_allowlist_from_http()
            self._allowlist = allowlist
            self._last_refresh_success = time.time()
            self._last_error = None
            logger.info(
                "IP allowlist refreshed from {} with {} entries",
                self.config.ip_allowlist_url,
                len(self._allowlist),
            )
        except Exception as exc:
            self._last_error = str(exc)
            if self._allowlist:
                logger.warning(
                    "Failed to refresh IP allowlist from {}: {}. Using last-known allowlist with {} entries.",
                    self.config.ip_allowlist_url,
                    exc,
                    len(self._allowlist),
                )
                return
            if self.config.ip_allowlist_fail_open:
                logger.warning(
                    "Failed to fetch IP allowlist from {}: {}. fail-open enabled; allowing all IPs.",
                    self.config.ip_allowlist_url,
                    exc,
                )
                return

            message = f"Unable to fetch IP allowlist from {self.config.ip_allowlist_url}: {exc}"
            if fail_hard:
                raise ValueError(message) from exc
            raise RuntimeError(message) from exc

    def _fetch_allowlist_from_http(self) -> List[IPAddressNetwork]:
        if not self.config.ip_allowlist_url:
            return list(self._allowlist)

        headers = {
            "Accept": "application/json, text/plain; q=0.9",
        }
        if self.config.ip_allowlist_bearer_token:
            headers["Authorization"] = f"Bearer {self.config.ip_allowlist_bearer_token}"

        request = urllib.request.Request(
            self.config.ip_allowlist_url,
            headers=headers,
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.ip_allowlist_http_timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise ValueError(f"HTTP status {status}")

                content_type = response.headers.get("Content-Type", "")
                payload = response.read().decode("utf-8", errors="replace")
                return _parse_allowlist_http_payload(payload, content_type)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"URL error: {exc.reason}") from exc


class JWTValidator:
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._jwks_client = None
        if config.sso_jwks_url:
            if PyJWKClient is None:
                raise ValueError("MCP_SSO_JWKS_URL requires PyJWT with PyJWKClient support")
            self._jwks_client = PyJWKClient(config.sso_jwks_url)

    def decode_token(self, token: str) -> Dict[str, Any]:
        if jwt is None:
            raise ValueError("PyJWT is not installed")

        decode_kwargs: Dict[str, Any] = {
            "algorithms": self.config.sso_jwt_algorithms,
            "options": {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": bool(self.config.sso_audience),
                "verify_iss": bool(self.config.sso_issuer),
            },
        }
        if self.config.sso_audience:
            decode_kwargs["audience"] = self.config.sso_audience
        if self.config.sso_issuer:
            decode_kwargs["issuer"] = self.config.sso_issuer

        if self._jwks_client is not None:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(token, signing_key.key, **decode_kwargs)

        return jwt.decode(token, self.config.sso_jwt_secret, **decode_kwargs)

    @staticmethod
    def extract_scopes(claims: Dict[str, Any]) -> Set[str]:
        scopes: Set[str] = set()
        for key in ("scope", "scp"):
            claim = claims.get(key)
            if isinstance(claim, str):
                scopes.update([item for item in claim.split() if item])
            elif isinstance(claim, list):
                scopes.update([str(item) for item in claim if str(item)])
        return scopes


class AuthAndIPMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: SecurityConfig):
        super().__init__(app)
        self.config = config
        self.jwt_validator = JWTValidator(config) if config.sso_enabled else None
        self.ip_allowlist_provider = IPAllowlistProvider(config) if config.ip_filter_enabled else None
        logger.info(
            "HTTP security middleware initialized: sso_enabled={}, ip_filter_enabled={}, ip_allowlist_url={}, trust_proxy_headers={}",
            self.config.sso_enabled,
            self.config.ip_filter_enabled,
            self.config.ip_allowlist_url or "",
            self.config.trust_proxy_headers,
        )

    def _extract_client_ip(self, request: Request) -> Optional[str]:
        if self.config.trust_proxy_headers:
            x_forwarded_for = request.headers.get("x-forwarded-for")
            if x_forwarded_for:
                first = x_forwarded_for.split(",")[0].strip()
                if first:
                    return first
            x_real_ip = request.headers.get("x-real-ip")
            if x_real_ip:
                return x_real_ip.strip()
        return request.client.host if request.client else None

    def _check_ip_allowlist(self, request: Request) -> Optional[Response]:
        if not self.config.ip_filter_enabled:
            return None

        try:
            allowlist = self.ip_allowlist_provider.get_allowlist()
        except RuntimeError as exc:
            return JSONResponse(
                {"error": "service_unavailable", "message": str(exc)},
                status_code=503,
            )

        if not allowlist and self.config.ip_allowlist_fail_open and self.config.ip_allowlist_url:
            return None
        if not allowlist:
            return JSONResponse(
                {"error": "forbidden", "message": "IP allowlist is empty, request denied"},
                status_code=403,
            )

        client_ip_str = self._extract_client_ip(request)
        if not client_ip_str:
            return JSONResponse({"error": "forbidden", "message": "Unable to determine client IP"}, status_code=403)

        try:
            client_ip = ipaddress.ip_address(client_ip_str)
        except ValueError:
            return JSONResponse(
                {"error": "forbidden", "message": f"Invalid client IP format: {client_ip_str}"},
                status_code=403,
            )

        for network in allowlist:
            if client_ip in network:
                return None

        return JSONResponse(
            {"error": "forbidden", "message": f"Client IP {client_ip} is not in MCP_IP_ALLOWLIST"},
            status_code=403,
        )

    def _check_sso(self, request: Request) -> Optional[Response]:
        if not self.config.sso_enabled:
            return None

        auth_header = request.headers.get("authorization", "")
        if not auth_header:
            return JSONResponse(
                {"error": "unauthorized", "message": "Missing Authorization header"},
                status_code=401,
            )

        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            return JSONResponse(
                {"error": "unauthorized", "message": "Authorization header must be Bearer token"},
                status_code=401,
            )

        token = parts[1].strip()
        try:
            claims = self.jwt_validator.decode_token(token)
        except InvalidTokenError as exc:
            return JSONResponse({"error": "unauthorized", "message": f"Invalid token: {exc}"}, status_code=401)
        except Exception as exc:
            logger.exception("SSO token verification failed unexpectedly")
            return JSONResponse(
                {"error": "unauthorized", "message": f"Token verification failed: {exc}"},
                status_code=401,
            )

        if self.config.sso_required_scopes:
            token_scopes = JWTValidator.extract_scopes(claims)
            missing = self.config.sso_required_scopes - token_scopes
            if missing:
                return JSONResponse(
                    {
                        "error": "unauthorized",
                        "message": f"Missing required scopes: {', '.join(sorted(missing))}",
                    },
                    status_code=401,
                )

        request.state.auth_claims = claims
        return None

    async def dispatch(self, request: Request, call_next):
        # Let CORS preflight pass through without auth checks.
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        ip_denied = self._check_ip_allowlist(request)
        if ip_denied is not None:
            return ip_denied

        auth_denied = self._check_sso(request)
        if auth_denied is not None:
            return auth_denied

        return await call_next(request)
