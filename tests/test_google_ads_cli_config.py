import os
import subprocess
import sys
from pathlib import Path

from src.providers.google_ads.config import check_google_ads_readiness


SCRIPT = Path("scripts") / "fetch_google_ads_api.py"


def test_readiness_reports_missing_env_vars_without_values():
    readiness = check_google_ads_readiness(
        profile="inn-at-spanish-head",
        environ={},
    )

    assert readiness.ready is False
    assert readiness.customer_id_source == "missing"
    assert "GOOGLE_ADS_DEVELOPER_TOKEN" in readiness.missing
    assert "GOOGLE_ADS_OAUTH_CLIENT_SECRETS" in readiness.missing
    assert "GOOGLE_ADS_OAUTH_TOKEN_FILE" in readiness.missing
    assert "SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID" in readiness.missing
    assert "mock-developer-token" not in str(readiness.to_safe_dict())
    assert "mock-client-secrets-path" not in str(readiness.to_safe_dict())


def test_readiness_recognizes_mocked_env_vars_and_cli_customer_id():
    env = {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "mock-developer-token",
        "GOOGLE_ADS_OAUTH_CLIENT_SECRETS": "mock-client-secrets-path",
        "GOOGLE_ADS_OAUTH_TOKEN_FILE": "mock-token-file",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "9999999999",
    }

    readiness = check_google_ads_readiness(
        profile="inn-at-spanish-head",
        customer_id="1234567890",
        environ=env,
    )

    assert readiness.ready is True
    assert readiness.customer_id_source == "cli"
    assert readiness.has_login_customer_id is True
    assert readiness.missing == []
    assert "mock-developer-token" not in str(readiness.to_safe_dict())


def test_readiness_uses_profile_specific_customer_id_env():
    env = {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "mock-developer-token",
        "GOOGLE_ADS_OAUTH_CLIENT_SECRETS": "mock-client-secrets-path",
        "GOOGLE_ADS_OAUTH_TOKEN_FILE": "mock-token-file",
        "SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID": "1234567890",
    }

    readiness = check_google_ads_readiness(profile="inn-at-spanish-head", environ=env)

    assert readiness.ready is True
    assert readiness.customer_id_source == "env"
    assert readiness.has_login_customer_id is False


def test_cli_dry_run_exits_successfully_without_credentials_and_writes_no_output(tmp_path):
    result = _run_cli(
        tmp_path,
        "--profile",
        "inn-at-spanish-head",
        "--customer-id",
        "1234567890",
        "--start-date",
        "2026-01-01",
        "--end-date",
        "2026-05-31",
        "--real-output",
        "--dry-run",
        env={},
    )

    assert result.returncode == 0
    assert "Google Ads API export dry run only." in result.stdout
    assert "No API calls were made." in result.stdout
    assert "No files were written." in result.stdout
    assert "Future output: exports\\local-real\\dashboard-lab\\inn-at-spanish-head\\google-ads-summary.json" in result.stdout
    assert "GOOGLE_ADS_DEVELOPER_TOKEN" in result.stdout
    assert "1234567890" not in result.stdout
    assert not (tmp_path / "exports").exists()


def test_cli_dry_run_handles_missing_customer_id_value_from_powershell_env(tmp_path):
    result = _run_cli(
        tmp_path,
        "--profile",
        "inn-at-spanish-head",
        "--customer-id",
        "--start-date",
        "2026-01-01",
        "--end-date",
        "2026-05-31",
        "--real-output",
        "--dry-run",
        env={},
    )

    assert result.returncode == 0
    assert "Credential readiness: missing" in result.stdout
    assert "SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID" in result.stdout
    assert "usage:" not in result.stderr
    assert not (tmp_path / "exports").exists()


def test_cli_non_dry_run_requires_real_output_before_future_write(tmp_path):
    result = _run_cli(
        tmp_path,
        "--profile",
        "inn-at-spanish-head",
        "--customer-id",
        "1234567890",
        "--start-date",
        "2026-01-01",
        "--end-date",
        "2026-05-31",
        env=_mock_ready_env(),
    )

    assert result.returncode == 1
    assert "--real-output is required" in result.stderr
    assert not (tmp_path / "exports").exists()


def test_cli_non_dry_run_fails_safely_when_mock_credential_files_are_missing(tmp_path):
    env = _mock_ready_env()
    result = _run_cli(
        tmp_path,
        "--profile",
        "inn-at-spanish-head",
        "--customer-id",
        "1234567890",
        "--start-date",
        "2026-01-01",
        "--end-date",
        "2026-05-31",
        "--real-output",
        env=env,
    )

    assert result.returncode == 1
    assert "could not be read" in result.stderr
    assert "mock-developer-token" not in result.stdout + result.stderr
    assert "mock-token-file" not in result.stdout + result.stderr
    assert "1234567890" not in result.stdout + result.stderr
    assert not (tmp_path / "exports").exists()


def _run_cli(tmp_path, *args, env):
    command = [sys.executable, str(Path.cwd() / SCRIPT), *args]
    merged_env = os.environ.copy()
    for key in list(merged_env):
        if key.startswith("GOOGLE_ADS_") or key.endswith("_GOOGLE_ADS_CUSTOMER_ID"):
            merged_env.pop(key)
    merged_env.update(env)
    return subprocess.run(
        command,
        cwd=tmp_path,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def _mock_ready_env():
    return {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "mock-developer-token",
        "GOOGLE_ADS_OAUTH_CLIENT_SECRETS": "mock-client-secrets-path",
        "GOOGLE_ADS_OAUTH_TOKEN_FILE": "mock-token-file",
    }
