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
from src.profile_local_config_writer import (
    ProfileLocalConfigWriteError,
    build_local_config_draft,
    preview_local_config_update,
    write_local_config_update,
)


def test_profile_local_config_path_resolves_by_slug(tmp_path):
    path = profile_local_config_path("inn-at-spanish-head", config_dir=tmp_path)

    assert path == tmp_path / "inn-at-spanish-head.local.json"


def test_profile_local_config_rejects_unsafe_slug(tmp_path):
    with pytest.raises(ProfileLocalConfigError):
        profile_local_config_path("../inn-at-spanish-head", config_dir=tmp_path)


def test_local_config_writer_builds_safe_missing_draft(tmp_path):
    draft = build_local_config_draft("inn-at-spanish-head", config_dir=tmp_path)

    assert draft["profile"] == "inn-at-spanish-head"
    assert draft["exists"] is False
    assert draft["draft"]["profile"] == "inn-at-spanish-head"
    assert draft["draft"]["google_ads_search"] == {"status": "planned"}
    assert draft["path_label"].endswith("inn-at-spanish-head.local.json")
    assert not (tmp_path / "inn-at-spanish-head.local.json").exists()


def test_local_config_writer_preview_normalizes_allowed_fields_without_writing(tmp_path):
    preview = preview_local_config_update(
        "inn-at-spanish-head",
        {
            "profile": "inn-at-spanish-head",
            "ga4": {
                "property_id_env": "INN_GA4_PROPERTY_ID",
                "oauth_client_secrets_env": "INN_GA4_CLIENT",
                "oauth_token_file_env": "INN_GA4_TOKEN",
            },
            "gsc": {
                "site_url": "sc-domain:spanishhead.com",
                "oauth_client_secrets_env": "INN_GSC_CLIENT",
                "oauth_token_file_env": "INN_GSC_TOKEN",
            },
            "local_falcon": {
                "manifest_path": "local-falcon-manifests/inn-at-spanish-head.json",
                "api_key_env": "LOCAL_FALCON_API_KEY",
            },
            "google_ads_search": {"status": "planned"},
        },
        config_dir=tmp_path,
    )

    payload = preview.as_safe_dict()
    assert preview.blocked is False
    assert payload["would_create"] is True
    assert payload["normalized_config"]["local_falcon"]["manifest_path"] == "local-falcon-manifests/inn-at-spanish-head.json"
    assert any(change["key"] == "property_id_env" for change in payload["changes"])
    assert not (tmp_path / "inn-at-spanish-head.local.json").exists()


def test_local_config_writer_accepts_expanded_safe_provider_metadata(tmp_path):
    preview = preview_local_config_update(
        "demo-profile",
        {
            "profile": "demo-profile",
            "google_ads_search": {
                "status": "planned",
                "customer_id_env": "DEMO_GOOGLE_ADS_CUSTOMER_ID",
                "developer_token_env": "DEMO_GOOGLE_ADS_DEVELOPER_TOKEN",
                "oauth_client_secrets_env": "DEMO_GOOGLE_ADS_CLIENT",
                "oauth_token_file_env": "DEMO_GOOGLE_ADS_TOKEN",
                "login_customer_id_env": "DEMO_GOOGLE_ADS_LOGIN_CUSTOMER_ID",
            },
            "callrail": {
                "local_input_filename": "calls.csv",
                "account_id_env": "DEMO_CALLRAIL_ACCOUNT_ID",
                "company_id_env": "DEMO_CALLRAIL_COMPANY_ID",
            },
            "form_fills": {"local_input_filename": "form-fills.json"},
        },
        config_dir=tmp_path,
    )

    payload = preview.as_safe_dict()
    serialized = json.dumps(payload)
    assert preview.blocked is False
    assert payload["normalized_config"]["google_ads_search"]["customer_id_env"] == "DEMO_GOOGLE_ADS_CUSTOMER_ID"
    assert payload["normalized_config"]["callrail"]["local_input_filename"] == "calls.csv"
    assert payload["normalized_config"]["form_fills"]["local_input_filename"] == "form-fills.json"
    assert "9999999999" not in serialized
    assert "developer-token-secret" not in serialized
    assert not (tmp_path / "demo-profile.local.json").exists()


def test_local_config_writer_rejects_invalid_env_secret_markers_and_raw_payloads(tmp_path):
    preview = preview_local_config_update(
        "inn-at-spanish-head",
        {
            "profile": "inn-at-spanish-head",
            "ga4": {
                "property_id_env": "lowercase_name",
                "oauth_client_secrets_env": '{"client_secret":"value"}',
                "oauth_token_file_env": "REFRESH_TOKEN_VALUE",
            },
            "local_falcon": {
                "manifest_path": "date,email\n2026-01-01,test@example.test",
                "api_key_env": "LOCAL_FALCON_API_KEY_VALUE",
            },
        },
        config_dir=tmp_path,
    )

    serialized = json.dumps(preview.as_safe_dict())
    assert preview.blocked is True
    assert "must be an uppercase environment variable name" in serialized
    assert "lowercase_name" not in serialized
    assert '{"client_secret":"value"}' not in serialized
    assert "test@example.test" not in serialized
    assert not (tmp_path / "inn-at-spanish-head.local.json").exists()


def test_local_config_writer_rejects_raw_ids_pii_and_path_traversal_for_new_fields(tmp_path):
    preview = preview_local_config_update(
        "demo-profile",
        {
            "profile": "demo-profile",
            "google_ads_search": {
                "customer_id_env": "1234567890",
                "developer_token_env": '{"developer_token":"value"}',
            },
            "callrail": {"local_input_filename": "../calls.csv"},
            "form_fills": {"local_input_filename": "name,email,message.csv"},
        },
        config_dir=tmp_path,
    )

    serialized = json.dumps(preview.as_safe_dict())
    assert preview.blocked is True
    assert "must be an uppercase environment variable name" in serialized
    assert "must be a simple filename" in serialized
    assert "looks like raw provider/customer data" in serialized
    assert "1234567890" not in serialized
    assert '{"developer_token":"value"}' not in serialized
    assert "name,email,message.csv" not in serialized
    assert not (tmp_path / "demo-profile.local.json").exists()


def test_local_config_writer_save_requires_confirmation_and_writes_temp_dir_only(tmp_path):
    draft = {
        "profile": "inn-at-spanish-head",
        "ga4": {"property_id_env": "INN_GA4_PROPERTY_ID"},
        "gsc": {"site_url": "https://spanishhead.com/"},
        "local_falcon": {"manifest_path": "local-falcon-manifests/inn-at-spanish-head.json"},
    }

    with pytest.raises(ProfileLocalConfigWriteError):
        write_local_config_update("inn-at-spanish-head", draft, confirmed=False, config_dir=tmp_path)

    response = write_local_config_update("inn-at-spanish-head", draft, confirmed=True, config_dir=tmp_path)
    path = tmp_path / "inn-at-spanish-head.local.json"

    assert response["saved"] is True
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["profile"] == "inn-at-spanish-head"
    assert payload["ga4"]["property_id_env"] == "INN_GA4_PROPERTY_ID"
    assert payload["google_ads_search"]["status"] == "planned"


def test_local_config_writer_merges_existing_config_predictably(tmp_path):
    path = tmp_path / "inn-at-spanish-head.local.json"
    path.write_text(
        json.dumps(
            {
                "profile": "inn-at-spanish-head",
                "ga4": {"property_id_env": "OLD_GA4_PROPERTY_ID"},
                "gsc": {"site_url": "https://spanishhead.com/"},
            }
        ),
        encoding="utf-8",
    )

    response = write_local_config_update(
        "inn-at-spanish-head",
        {"profile": "inn-at-spanish-head", "ga4": {"oauth_token_file_env": "INN_GA4_TOKEN"}},
        confirmed=True,
        config_dir=tmp_path,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert response["saved"] is True
    assert payload["ga4"]["property_id_env"] == "OLD_GA4_PROPERTY_ID"
    assert payload["ga4"]["oauth_token_file_env"] == "INN_GA4_TOKEN"
    assert payload["gsc"]["site_url"] == "https://spanishhead.com/"


def test_local_config_writer_rejects_profile_mismatch_and_path_escape(tmp_path):
    path = tmp_path / "inn-at-spanish-head.local.json"
    path.write_text(json.dumps({"profile": "aluma-seo-geo"}), encoding="utf-8")

    with pytest.raises(ProfileLocalConfigWriteError):
        preview_local_config_update("inn-at-spanish-head", {"profile": "inn-at-spanish-head"}, config_dir=tmp_path)

    with pytest.raises(ProfileLocalConfigError):
        build_local_config_draft("../inn-at-spanish-head", config_dir=tmp_path)


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
                "google_ads_search": {
                    "status": "planned",
                    "customer_id_env": "INN_GOOGLE_ADS_CUSTOMER_ID",
                    "developer_token_env": "INN_GOOGLE_ADS_DEVELOPER_TOKEN",
                    "oauth_client_secrets_env": "INN_GOOGLE_ADS_CLIENT",
                    "oauth_token_file_env": "INN_GOOGLE_ADS_TOKEN",
                },
                "callrail": {"local_input_filename": "calls.csv"},
                "form_fills": {"local_input_filename": "form-fills.csv"},
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
            "INN_GOOGLE_ADS_CUSTOMER_ID": "secret-customer-id",
            "INN_GOOGLE_ADS_DEVELOPER_TOKEN": "secret-developer-token",
            "INN_GOOGLE_ADS_CLIENT": str(client),
            "INN_GOOGLE_ADS_TOKEN": str(token),
        },
    )

    ga4 = config.provider("ga4")
    gsc = config.provider("gsc")
    local_falcon = config.provider("local_falcon")
    google_ads = config.provider("google_ads_search")
    callrail = config.provider("callrail")
    form_fills = config.provider("form_fills")
    serialized = json.dumps(config.as_safe_dict())
    assert ga4["property_id_env_present"] is True
    assert ga4["oauth_client_secrets_file_exists"] is True
    assert ga4["oauth_token_file_exists"] is True
    assert gsc["site_url_configured"] is True
    assert local_falcon["manifest_exists"] is True
    assert local_falcon["api_key_env_present"] is True
    assert google_ads["customer_id_env_present"] is True
    assert google_ads["developer_token_env_present"] is True
    assert google_ads["credentials_configured"] is True
    assert callrail["input_path"] is True
    assert form_fills["input_csv"] is True
    assert "secret-property-id" not in serialized
    assert "secret-api-key" not in serialized
    assert "secret-customer-id" not in serialized
    assert "secret-developer-token" not in serialized
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


def test_profile_alias_local_config_takes_alias_file_before_canonical(tmp_path):
    alias_config = tmp_path / "aluma.local.json"
    canonical_config = tmp_path / "aluma-seo-geo.local.json"
    alias_config.write_text(
        json.dumps(
            {
                "profile": "aluma",
                "ga4": {"property_id": "111111111"},
            }
        ),
        encoding="utf-8",
    )
    canonical_config.write_text(
        json.dumps(
            {
                "profile": "aluma-seo-geo",
                "ga4": {"property_id": "222222222"},
            }
        ),
        encoding="utf-8",
    )

    config = load_profile_local_config("aluma", config_dir=tmp_path, env={})

    assert config.requested_profile_slug == "aluma"
    assert config.profile_slug == "aluma-seo-geo"
    assert config.path == alias_config
    assert config.provider("ga4")["property_id_configured"] is True
    assert config.provider("ga4")["property_id_source"] == "local_config"


def test_load_ga4_config_can_use_alias_direct_local_config_values(tmp_path, monkeypatch):
    client = tmp_path.parent / "client.json"
    token = tmp_path.parent / "token.json"
    client.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    config_dir = tmp_path / "local-profile-configs"
    config_dir.mkdir()
    (config_dir / "aluma.local.json").write_text(
        json.dumps(
            {
                "profile": "aluma",
                "ga4": {
                    "property_id": "123456789",
                    "oauth_client_secrets_file": str(client),
                    "oauth_token_file": str(token),
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "DEFAULT_LOCAL_PROFILE_CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "load_local_operator_config", lambda: None)
    monkeypatch.delenv("MUSIMACK_GA4_PROPERTY_ID", raising=False)
    monkeypatch.delenv("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS", raising=False)
    monkeypatch.delenv("MUSIMACK_GA4_OAUTH_TOKEN_FILE", raising=False)

    config = load_ga4_config("aluma")

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
