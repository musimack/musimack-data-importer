from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


REQUIRED_ENV_VARS = [
    "MUSIMACK_GA4_AUTH_METHOD",
    "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS",
    "MUSIMACK_GA4_OAUTH_TOKEN_FILE",
    "MUSIMACK_PORTAL_DATABASE_URL",
]


@dataclass(frozen=True)
class ReadinessCheck:
    level: str
    check: str
    message: str

    @property
    def failed(self) -> bool:
        return self.level == "FAIL"

    def line(self) -> str:
        return f"{self.level}: {self.check} - {self.message}"


def build_oauth_readiness_report(
    env: Mapping[str, str] | None = None,
) -> list[ReadinessCheck]:
    env = os.environ if env is None else env
    checks: list[ReadinessCheck] = []

    checks.extend(_check_required_env(env))
    auth_method = _env_value(env, "MUSIMACK_GA4_AUTH_METHOD")
    if auth_method:
        if auth_method.lower() == "oauth":
            checks.append(ReadinessCheck("PASS", "auth method", "MUSIMACK_GA4_AUTH_METHOD is oauth"))
        else:
            checks.append(
                ReadinessCheck(
                    "FAIL",
                    "auth method",
                    "MUSIMACK_GA4_AUTH_METHOD must be oauth for this operator flow",
                )
            )

    client_path_text = _env_value(env, "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS")
    if client_path_text:
        checks.extend(_check_client_secrets_file(Path(client_path_text)))

    token_path_text = _env_value(env, "MUSIMACK_GA4_OAUTH_TOKEN_FILE")
    if token_path_text:
        checks.extend(_check_token_cache_path(Path(token_path_text)))

    if _env_value(env, "MUSIMACK_PORTAL_DATABASE_URL"):
        checks.append(
            ReadinessCheck(
                "PASS",
                "portal database env",
                "MUSIMACK_PORTAL_DATABASE_URL is present; value not printed",
            )
        )

    checks.append(
        ReadinessCheck(
            "WARN",
            "operator shell",
            "If browser auth is needed, run bootstrap from normal local PowerShell, not an isolated shell that cannot open a browser or write the token cache.",
        )
    )
    return checks


def report_has_failures(checks: list[ReadinessCheck]) -> bool:
    return any(check.failed for check in checks)


def _check_required_env(env: Mapping[str, str]) -> list[ReadinessCheck]:
    checks = []
    for name in REQUIRED_ENV_VARS:
        if _env_value(env, name):
            checks.append(ReadinessCheck("PASS", "environment", f"{name} is present"))
        else:
            checks.append(ReadinessCheck("FAIL", "environment", f"{name} is missing"))
    return checks


def _check_client_secrets_file(path: Path) -> list[ReadinessCheck]:
    checks = []
    if not path.exists():
        return [
            ReadinessCheck(
                "FAIL",
                "OAuth client secrets file",
                "Path from MUSIMACK_GA4_OAUTH_CLIENT_SECRETS does not exist",
            )
        ]
    if not path.is_file():
        return [
            ReadinessCheck(
                "FAIL",
                "OAuth client secrets file",
                "Path from MUSIMACK_GA4_OAUTH_CLIENT_SECRETS is not a file",
            )
        ]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return [
            ReadinessCheck(
                "FAIL",
                "OAuth client secrets file",
                "Path from MUSIMACK_GA4_OAUTH_CLIENT_SECRETS is not readable",
            )
        ]

    checks.append(
        ReadinessCheck(
            "PASS",
            "OAuth client secrets file",
            "Path exists and is readable; contents not printed",
        )
    )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        checks.append(
            ReadinessCheck(
                "FAIL",
                "OAuth client secrets JSON",
                "Client secrets file is not valid JSON",
            )
        )
        return checks

    if _client_secrets_shape_ok(payload):
        checks.append(
            ReadinessCheck(
                "PASS",
                "OAuth client secrets JSON",
                "Client secrets JSON has expected installed/web app structure; secret values not printed",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                "FAIL",
                "OAuth client secrets JSON",
                "Client secrets JSON must include an installed or web OAuth client with client_id, auth_uri, token_uri, and client_secret fields",
            )
        )
    return checks


def _client_secrets_shape_ok(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    client = payload.get("installed") or payload.get("web")
    if not isinstance(client, dict):
        return False
    required = {"client_id", "auth_uri", "token_uri", "client_secret"}
    return required.issubset(client.keys())


def _check_token_cache_path(path: Path) -> list[ReadinessCheck]:
    checks = []
    parent = path.parent if str(path.parent) else Path(".")
    if not parent.exists():
        return [
            ReadinessCheck(
                "FAIL",
                "OAuth token cache directory",
                "Parent directory from MUSIMACK_GA4_OAUTH_TOKEN_FILE does not exist; create it before bootstrap/export",
            )
        ]
    if not parent.is_dir():
        return [
            ReadinessCheck(
                "FAIL",
                "OAuth token cache directory",
                "Parent path from MUSIMACK_GA4_OAUTH_TOKEN_FILE is not a directory",
            )
        ]

    if _directory_writable(parent):
        checks.append(
            ReadinessCheck(
                "PASS",
                "OAuth token cache directory",
                "Parent directory exists and is writable",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                "FAIL",
                "OAuth token cache directory",
                "Parent directory is not writable; OAuth token creation or refresh may fail",
            )
        )

    if not path.exists():
        checks.append(
            ReadinessCheck(
                "WARN",
                "OAuth token cache file",
                "Token file does not exist; interactive OAuth bootstrap/export may open browser login and create it",
            )
        )
        return checks

    if not path.is_file():
        checks.append(
            ReadinessCheck(
                "FAIL",
                "OAuth token cache file",
                "Token path exists but is not a file",
            )
        )
        return checks

    try:
        path.read_text(encoding="utf-8")
    except OSError:
        checks.append(
            ReadinessCheck(
                "FAIL",
                "OAuth token cache file",
                "Token file exists but is not readable; contents not printed",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                "PASS",
                "OAuth token cache file",
                "Token file exists and is readable; contents not printed",
            )
        )

    if os.access(path, os.W_OK):
        checks.append(
            ReadinessCheck(
                "PASS",
                "OAuth token cache file",
                "Token file is writable for refresh updates",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                "WARN",
                "OAuth token cache file",
                "Token file is not writable; valid tokens may work, but refresh or re-auth will fail",
            )
        )
    return checks


def _directory_writable(path: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path,
            prefix=".ga4-readiness-",
            suffix=".tmp",
            delete=True,
        ) as handle:
            handle.write("ok")
        return True
    except OSError:
        return False


def _env_value(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    return value.strip() if value and value.strip() else None
