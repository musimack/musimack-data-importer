import json
from datetime import date
from pathlib import Path

import pytest

import src.config as config_module
from scripts.pull_ga4_traffic_overview import _resolve_ga4_output_path
from src.config import DateRange, load_ga4_config
from src.profile_local_config import (
    ProfileLocalConfigError,
    load_profile_local_config,
    profile_local_config_path,
)


def test_profile_local_config_path_resolves_by_slug(tmp_path):
    path = profile_local_config_path("inn-at-spanish-head", config_dir=tmp_path)

    assert path == tmp_path / "inn-at-spanish-head.local.json"


def test_profile_local_config_rejects_unsafe_slug(tmp_path):
    with pytest.raises(ProfileLocalConfigError):
        profile_local_config_path("../inn-at-spanish-head", config_dir=tmp_path)


def test_missing_profile_local_config_is_safe(tmp_path):
    config = load_profile_local_config("inn-at-spanish-head", config_dir=tmp_path, env={})

    assert config.found is False
    assert config.valid is True
    assert config.path_label.endswith("inn-at-spanish-head.local.json")
    assert config.provider("ga4")["_local_profile_config"]["present"] is False


def test_malformed_profile_local_config_returns_safe_error(tmp_path):
    path = tmp_path / "inn-at-spanish-head.local.json"
    path.write_text("{bad json", encoding="utf-8")

    config = load_profile_local_config("inn-at-spanish-head", config_dir=tmp_path, env={})

    assert config.found is True
    assert config.valid is False
    assert config.error == "local profile config is not valid JSON"
    assert "bad json" not in json.dumps(config.as_safe_dict())


def test_profile_local_config_checks_env_presence_and_file_existence(tmp_path):
    client = tmp_path / "client.json"
    token = tmp_path / "token.json"
    manifest = tmp_path / "local-falcon-manifests" / "inn-at-spanish-head.json"
    client.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    manifest.parent.mkdir()
    manifest.write_text("{}", encoding="utf-8")
    path = tmp_path / "inn-at-spanish-head.local.json"
    path.write_text(
        json.dumps(
            {
                "profile": "inn-at-spanish-head",
                "ga4": {
                    "property_id_env": "INN_GA4_PROPERTY_ID",
                    "oauth_client_secrets_env": "INN_GA4_CLIENT",
                    "oauth_token_file_env": "INN_GA4_TOKEN",
                },
                "gsc": {
                    "site_url": "https://spanishhead.com/",
                    "oauth_client_secrets_env": "INN_GSC_CLIENT",
                    "oauth_token_file_env": "INN_GSC_TOKEN",
                },
                "local_falcon": {
                    "manifest_path": str(manifest),
                    "api_key_env": "INN_LOCAL_FALCON_API_KEY",
                },
                "google_ads_search": {"status": "planned"},
            }
        ),
        encoding="utf-8",
    )

    config = load_profile_local_config(
        "inn-at-spanish-head",
        config_dir=tmp_path,
        env={
            "INN_GA4_PROPERTY_ID": "secret-property-id",
            "INN_GA4_CLIENT": str(client),
            "INN_GA4_TOKEN": str(token),
            "INN_GSC_CLIENT": str(client),
            "INN_GSC_TOKEN": str(token),
            "INN_LOCAL_FALCON_API_KEY": "secret-api-key",
        },
    )

    ga4 = config.provider("ga4")
    gsc = config.provider("gsc")
    local_falcon = config.provider("local_falcon")
    serialized = json.dumps(config.as_safe_dict())
    assert ga4["property_id_env_present"] is True
    assert ga4["oauth_client_secrets_file_exists"] is True
    assert ga4["oauth_token_file_exists"] is True
    assert gsc["site_url_configured"] is True
    assert local_falcon["manifest_exists"] is True
    assert local_falcon["api_key_env_present"] is True
    assert "secret-property-id" not in serialized
    assert "secret-api-key" not in serialized
    assert str(client) not in serialized
    assert str(token) not in serialized


def test_profile_local_config_detects_profile_mismatch(tmp_path):
    path = tmp_path / "inn-at-spanish-head.local.json"
    path.write_text(json.dumps({"profile": "aluma-seo-geo"}), encoding="utf-8")

    config = load_profile_local_config("inn-at-spanish-head", config_dir=tmp_path, env={})

    assert config.valid is False
    assert config.error == "local profile config profile does not match requested slug"


def test_load_ga4_config_can_use_profile_env_names(tmp_path, monkeypatch):
    client = tmp_path / "client.json"
    token = tmp_path / "token.json"
    client.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    config_dir = tmp_path / "local-profile-configs"
    config_dir.mkdir()
    (config_dir / "inn-at-spanish-head.local.json").write_text(
        json.dumps(
            {
                "profile": "inn-at-spanish-head",
                "ga4": {
                    "property_id_env": "INN_GA4_PROPERTY_ID",
                    "oauth_client_secrets_env": "INN_GA4_CLIENT",
                    "oauth_token_file_env": "INN_GA4_TOKEN",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "DEFAULT_LOCAL_PROFILE_CONFIG_DIR", config_dir)
    monkeypatch.setenv("INN_GA4_PROPERTY_ID", "123456789")
    monkeypatch.setenv("INN_GA4_CLIENT", str(client))
    monkeypatch.setenv("INN_GA4_TOKEN", str(token))

    config = load_ga4_config("inn-at-spanish-head")

    assert config.property_id == "123456789"
    assert config.oauth_client_secrets_file == str(client)
    assert config.oauth_token_file == str(token)


def test_ga4_real_output_path_uses_profile_folder():
    path = _resolve_ga4_output_path(
        "inn-at-spanish-head",
        None,
        True,
        DateRange(date(2026, 1, 1), date(2026, 1, 31)),
    )

    assert path.as_posix() == "exports/local-real/dashboard-lab/inn-at-spanish-head/ga4-snapshot.json"
