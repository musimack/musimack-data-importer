from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import create_app
from src.local_secret_vault import DEFAULT_VAULT_PATH, LocalSecretVault
from src.operator_console import DEFAULT_PROFILE_REGISTRY, EXPECTED_DASHBOARD_FILES


def test_health_endpoint_returns_safe_status(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "app": "musimack-data-importer-local-api"}


def test_profile_registry_new_draft_returns_safe_options(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profile-registry/new-draft")

    assert response.status_code == 200
    payload = response.json()
    assert "ga4" in payload["draft"]["data_sources"]
    assert any(item["key"] == "google_ads_search" for item in payload["provider_options"])
    assert any(item["key"] == "content" for item in payload["capability_options"])
    assert "Do not enter secrets" in payload["warnings"][0]


def test_profile_registry_preview_returns_safe_profile_without_writing(tmp_path):
    registry = _registry(tmp_path)
    client = TestClient(create_app(registry_path=registry, env={}))
    draft = _new_profile_draft()

    response = client.post("/api/profile-registry/preview", json={"draft": draft})

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    assert payload["blocked"] is False
    assert payload["profile"]["slug"] == "new-client"
    assert payload["profile"]["dashboard_lab_route"] == "/lab/new-client"
    assert "google-ads-summary.json" in payload["expected_files"]
    assert "ga4-snapshot.json" not in payload["expected_files"]
    assert "new-client" not in json.dumps(json.loads(registry.read_text(encoding="utf-8")))
    assert str(registry.parent) not in serialized


def test_profile_registry_save_requires_confirmation_and_writes_temp_registry_only(tmp_path):
    registry = _registry(tmp_path)
    client = TestClient(create_app(registry_path=registry, env={}))
    draft = _new_profile_draft()

    unconfirmed = client.post("/api/profile-registry", json={"draft": draft})
    confirmed = client.post("/api/profile-registry", json={"draft": draft, "confirmed": True})

    assert unconfirmed.status_code == 400
    assert confirmed.status_code == 200
    payload = confirmed.json()
    assert payload["saved"] is True
    registry_payload = json.loads(registry.read_text(encoding="utf-8"))
    assert [item["slug"] for item in registry_payload["profiles"]] == ["demo-profile", "new-client"]
    assert str(registry.parent) not in json.dumps(payload)


def test_profile_registry_api_rejects_unsafe_drafts_without_echoing_values(tmp_path):
    registry = _registry(tmp_path)
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post(
        "/api/profile-registry/preview",
        json={
            "draft": {
                "slug": "demo-profile",
                "display_name": '{"client_secret":"value"}',
                "domain": "example.com",
                "vertical": "local service",
                "service_model": "SEO/GEO",
                "data_sources": ["ga4", "not_allowed"],
                "capabilities": [{"key": "content", "status": "active"}, {"key": "not_allowed", "status": "enabled"}],
                "dashboard_lab_route": "/lab/not-allowed",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    assert payload["blocked"] is True
    assert "slug already exists" in serialized
    assert "not allowed" in serialized
    assert "not editable" in serialized
    assert "capability status must be enabled or planned" in serialized
    assert '{"client_secret":"value"}' not in serialized
    assert "/lab/not-allowed" not in serialized


def test_profile_registry_env_override_preview_and_save_use_disposable_registry(tmp_path):
    seed_registry = _registry(tmp_path)
    override_registry = tmp_path / "override" / "dashboard_lab_profiles.qa.json"
    override_registry.parent.mkdir()
    override_registry.write_text(seed_registry.read_text(encoding="utf-8"), encoding="utf-8")
    default_before = DEFAULT_PROFILE_REGISTRY.read_text(encoding="utf-8")
    client = TestClient(
        create_app(
            env={"MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH": str(override_registry)},
        )
    )
    draft = _new_profile_draft()

    preview = client.post("/api/profile-registry/preview", json={"draft": draft})
    preview_payload = preview.json()
    after_preview = json.loads(override_registry.read_text(encoding="utf-8"))
    saved = client.post("/api/profile-registry", json={"draft": draft, "confirmed": True})
    saved_payload = saved.json()
    after_save = json.loads(override_registry.read_text(encoding="utf-8"))

    assert preview.status_code == 200
    assert saved.status_code == 200
    assert preview_payload["registry_path_label"] == "dashboard_lab_profiles.qa.json"
    assert saved_payload["registry_path_label"] == "dashboard_lab_profiles.qa.json"
    assert "new-client" not in json.dumps(after_preview)
    assert [item["slug"] for item in after_save["profiles"]] == ["demo-profile", "new-client"]
    assert DEFAULT_PROFILE_REGISTRY.read_text(encoding="utf-8") == default_before
    serialized = json.dumps({"preview": preview_payload, "saved": saved_payload})
    assert str(override_registry) not in serialized
    assert str(override_registry.parent) not in serialized


def test_profile_registry_explicit_injection_beats_env_override(tmp_path):
    explicit_registry = _registry(tmp_path)
    env_registry = tmp_path / "override" / "dashboard_lab_profiles.qa.json"
    env_registry.parent.mkdir()
    env_registry.write_text(explicit_registry.read_text(encoding="utf-8"), encoding="utf-8")
    client = TestClient(
        create_app(
            registry_path=explicit_registry,
            env={"MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH": str(env_registry)},
        )
    )
    draft = _new_profile_draft()

    response = client.post("/api/profile-registry", json={"draft": draft, "confirmed": True})

    assert response.status_code == 200
    explicit_payload = json.loads(explicit_registry.read_text(encoding="utf-8"))
    env_payload = json.loads(env_registry.read_text(encoding="utf-8"))
    assert [item["slug"] for item in explicit_payload["profiles"]] == ["demo-profile", "new-client"]
    assert [item["slug"] for item in env_payload["profiles"]] == ["demo-profile"]


def test_secret_vault_status_missing_temp_vault_does_not_create_file(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    response = client.get("/api/secrets/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["exists"] is False
    assert payload["unlocked"] is False
    assert payload["entries"] == []
    assert payload["entry_count"] == 0
    assert not vault_path.exists()


def test_secret_vault_unlock_can_create_missing_temp_vault_without_returning_passphrase(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    passphrase = "fake test passphrase"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    response = client.post(
        "/api/secrets/unlock",
        json={"passphrase": passphrase, "create_if_missing": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["exists"] is True
    assert payload["unlocked"] is True
    assert payload["entries"] == []
    assert vault_path.exists()
    assert passphrase not in json.dumps(payload)


def test_secret_vault_lock_reports_locked_status(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))
    client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake test passphrase", "create_if_missing": True},
    )

    response = client.post("/api/secrets/lock")

    assert response.status_code == 200
    payload = response.json()
    assert payload["exists"] is True
    assert payload["unlocked"] is False


def test_secret_vault_unlock_wrong_passphrase_returns_controlled_error(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    LocalSecretVault.create(vault_path, passphrase="fake correct passphrase")
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    response = client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake wrong passphrase"},
    )

    assert response.status_code == 401
    serialized = json.dumps(response.json())
    assert "fake correct passphrase" not in serialized
    assert "fake wrong passphrase" not in serialized
    assert "invalid" in response.json()["detail"]


def test_secret_vault_status_with_fake_secret_returns_safe_metadata_only(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    passphrase = "fake test passphrase"
    fake_secret = "fake-secret-value"
    vault = LocalSecretVault.create(vault_path, passphrase=passphrase)
    vault.set_secret(
        profile="demo-profile",
        provider="local_falcon",
        key="api_key",
        value=fake_secret,
    )
    vault.lock()
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    status_response = client.get("/api/secrets/status")
    unlock_response = client.post("/api/secrets/unlock", json={"passphrase": passphrase})

    assert status_response.status_code == 200
    assert unlock_response.status_code == 200
    status_payload = status_response.json()
    unlock_payload = unlock_response.json()
    assert status_payload["exists"] is True
    assert status_payload["unlocked"] is False
    assert status_payload["entries"][0]["profile"] == "demo-profile"
    assert status_payload["entries"][0]["provider"] == "local_falcon"
    assert status_payload["entries"][0]["key"] == "api_key"
    assert unlock_payload["unlocked"] is True
    serialized = json.dumps({"status": status_payload, "unlock": unlock_payload})
    assert fake_secret not in serialized
    assert passphrase not in serialized
    assert "ciphertext" not in serialized
    assert '"value_returned": false' in serialized


def test_secret_vault_corrupt_temp_vault_returns_safe_status_and_error(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    vault_path.write_text("{raw corrupt vault contents", encoding="utf-8")
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    status_response = client.get("/api/secrets/status")
    unlock_response = client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake test passphrase"},
    )

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["exists"] is True
    assert status_payload["unlocked"] is False
    assert status_payload["status"] == "error"
    assert status_payload["entries"] == []
    assert unlock_response.status_code == 400
    serialized = json.dumps({"status": status_payload, "unlock": unlock_response.json()})
    assert "raw corrupt vault contents" not in serialized
    assert "fake test passphrase" not in serialized


def test_secret_vault_env_override_is_used_without_leaking_path_or_creating_default(tmp_path, monkeypatch):
    disposable_cwd = tmp_path / "repo-cwd"
    disposable_cwd.mkdir()
    monkeypatch.chdir(disposable_cwd)
    override_path = tmp_path / "manual-qa" / "vault.local.json"
    passphrase = "fake test passphrase"
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"MUSIMACK_IMPORTER_VAULT_PATH": str(override_path)},
        )
    )

    missing = client.get("/api/secrets/status")
    created = client.post(
        "/api/secrets/unlock",
        json={"passphrase": passphrase, "create_if_missing": True},
    )

    assert missing.status_code == 200
    assert missing.json()["exists"] is False
    assert created.status_code == 200
    assert created.json()["exists"] is True
    assert created.json()["unlocked"] is True
    assert override_path.exists()
    assert not (disposable_cwd / DEFAULT_VAULT_PATH).exists()
    serialized = json.dumps({"missing": missing.json(), "created": created.json()})
    assert str(override_path) not in serialized
    assert "manual-qa" not in serialized
    assert passphrase not in serialized


def test_secret_vault_explicit_test_path_takes_precedence_over_env_override(tmp_path):
    explicit_path = tmp_path / "explicit" / "vault.local.json"
    ignored_override_path = tmp_path / "ignored-override" / "vault.local.json"
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"MUSIMACK_IMPORTER_VAULT_PATH": str(ignored_override_path)},
            secret_vault_path=explicit_path,
        )
    )

    response = client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake test passphrase", "create_if_missing": True},
    )

    assert response.status_code == 200
    assert explicit_path.exists()
    assert not ignored_override_path.exists()
    assert str(explicit_path) not in json.dumps(response.json())


def test_profile_local_falcon_api_key_can_be_saved_to_unlocked_temp_vault_safely(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    fake_key = "fake-local-falcon-api-key"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))
    client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake test passphrase", "create_if_missing": True},
    )

    response = client.post(
        "/api/profiles/demo-profile/secrets/local_falcon/api_key",
        json={"value": fake_key},
    )
    status = client.get("/api/profiles/demo-profile/secrets")

    assert response.status_code == 200
    assert status.status_code == 200
    secret = response.json()["secret"]
    assert secret["configured"] is True
    assert secret["profile"] == "demo-profile"
    assert secret["provider"] == "local_falcon"
    assert secret["key"] == "api_key"
    assert secret["classification"] == "secret"
    assert secret["source"] == "vault"
    assert secret["value_returned"] is False
    listed = status.json()["secrets"][0]
    assert listed["configured"] is True
    serialized = json.dumps({"response": response.json(), "status": status.json()})
    assert fake_key not in serialized
    assert "ciphertext" not in serialized


def test_profile_local_falcon_api_key_delete_removes_configured_status(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))
    client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake test passphrase", "create_if_missing": True},
    )
    client.post(
        "/api/profiles/demo-profile/secrets/local_falcon/api_key",
        json={"value": "fake-local-falcon-api-key"},
    )

    response = client.delete("/api/profiles/demo-profile/secrets/local_falcon/api_key")
    status = client.get("/api/profiles/demo-profile/secrets")

    assert response.status_code == 200
    assert response.json()["secret"]["configured"] is False
    assert status.json()["secrets"][0]["configured"] is False


def test_profile_local_falcon_api_key_delete_allows_local_frontend_preflight(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=tmp_path / "vault.local.json"))

    response = client.options(
        "/api/profiles/demo-profile/secrets/local_falcon/api_key",
        headers={
            "Origin": "http://127.0.0.1:5274",
            "Access-Control-Request-Method": "DELETE",
        },
    )

    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_profile_local_falcon_api_key_save_and_delete_require_unlocked_vault(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    LocalSecretVault.create(vault_path, passphrase="fake test passphrase").lock()
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    save = client.post(
        "/api/profiles/demo-profile/secrets/local_falcon/api_key",
        json={"value": "fake-local-falcon-api-key"},
    )
    delete = client.delete("/api/profiles/demo-profile/secrets/local_falcon/api_key")

    assert save.status_code == 423
    assert delete.status_code == 423
    serialized = json.dumps({"save": save.json(), "delete": delete.json()})
    assert "fake-local-falcon-api-key" not in serialized
    assert "ciphertext" not in serialized


def test_profile_secret_disallowed_provider_or_key_is_rejected(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))
    client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake test passphrase", "create_if_missing": True},
    )

    wrong_provider = client.post(
        "/api/profiles/demo-profile/secrets/google_ads_search/developer_token",
        json={"value": "fake-disallowed-secret"},
    )
    wrong_key = client.delete("/api/profiles/demo-profile/secrets/local_falcon/report_id")

    assert wrong_provider.status_code == 400
    assert wrong_key.status_code == 400
    serialized = json.dumps({"wrong_provider": wrong_provider.json(), "wrong_key": wrong_key.json()})
    assert "fake-disallowed-secret" not in serialized


def test_profile_secret_invalid_profile_is_rejected(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    status = client.get("/api/profiles/missing-profile/secrets")
    save = client.post(
        "/api/profiles/missing-profile/secrets/local_falcon/api_key",
        json={"value": "fake-local-falcon-api-key"},
    )

    assert status.status_code == 404
    assert save.status_code == 404
    assert "fake-local-falcon-api-key" not in json.dumps(save.json())


def test_profile_secret_wrong_passphrase_response_does_not_include_fake_key(tmp_path):
    vault_path = tmp_path / "vault.local.json"
    fake_key = "fake-local-falcon-api-key"
    vault = LocalSecretVault.create(vault_path, passphrase="fake correct passphrase")
    vault.set_secret(profile="demo-profile", provider="local_falcon", key="api_key", value=fake_key)
    vault.lock()
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, secret_vault_path=vault_path))

    response = client.post("/api/secrets/unlock", json={"passphrase": "fake wrong passphrase"})

    assert response.status_code == 401
    serialized = json.dumps(response.json())
    assert fake_key not in serialized
    assert "ciphertext" not in serialized


def test_profile_secret_env_override_does_not_create_default_vault_path(tmp_path, monkeypatch):
    disposable_cwd = tmp_path / "repo-cwd"
    disposable_cwd.mkdir()
    monkeypatch.chdir(disposable_cwd)
    override_path = tmp_path / "override" / "vault.local.json"
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"MUSIMACK_IMPORTER_VAULT_PATH": str(override_path)},
        )
    )
    client.post(
        "/api/secrets/unlock",
        json={"passphrase": "fake test passphrase", "create_if_missing": True},
    )
    response = client.post(
        "/api/profiles/demo-profile/secrets/local_falcon/api_key",
        json={"value": "fake-local-falcon-api-key"},
    )

    assert response.status_code == 200
    assert override_path.exists()
    assert not (disposable_cwd / DEFAULT_VAULT_PATH).exists()
    serialized = json.dumps(response.json())
    assert str(override_path) not in serialized
    assert "fake-local-falcon-api-key" not in serialized


def test_local_config_draft_for_known_profile_returns_safe_metadata(tmp_path):
    config_dir = tmp_path / "local-profile-configs"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, local_profile_config_dir=config_dir))

    response = client.get("/api/profiles/demo-profile/local-config/draft")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"] == "demo-profile"
    assert payload["exists"] is False
    assert payload["draft"]["profile"] == "demo-profile"
    assert payload["draft"]["google_ads_search"] == {"status": "planned"}
    assert payload["path_label"].endswith("demo-profile.local.json")
    assert str(config_dir) not in json.dumps(payload)
    assert not (config_dir / "demo-profile.local.json").exists()


def test_local_config_draft_unknown_profile_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, local_profile_config_dir=tmp_path))

    response = client.get("/api/profiles/missing-profile/local-config/draft")

    assert response.status_code == 404


def test_local_config_preview_returns_safe_changes_without_writing(tmp_path):
    config_dir = tmp_path / "local-profile-configs"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, local_profile_config_dir=config_dir))

    response = client.post(
        "/api/profiles/demo-profile/local-config/preview",
        json={
            "draft": {
                "profile": "demo-profile",
                "ga4": {"property_id_env": "DEMO_GA4_PROPERTY_ID"},
                "gsc": {"site_url": "https://demo.example.test/"},
                "local_falcon": {"manifest_path": "local-falcon-manifests/demo-profile.json"},
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["blocked"] is False
    assert payload["would_create"] is True
    assert any(change["key"] == "property_id_env" for change in payload["changes"])
    serialized = json.dumps(payload)
    assert str(config_dir) not in serialized
    assert not (config_dir / "demo-profile.local.json").exists()


def test_local_config_save_requires_confirmation_and_writes_temp_config_only(tmp_path):
    config_dir = tmp_path / "local-profile-configs"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, local_profile_config_dir=config_dir))
    draft = {
        "profile": "demo-profile",
        "ga4": {"property_id_env": "DEMO_GA4_PROPERTY_ID"},
        "gsc": {"site_url": "sc-domain:demo.example.test"},
        "local_falcon": {"manifest_path": "local-falcon-manifests/demo-profile.json"},
    }

    unconfirmed = client.post("/api/profiles/demo-profile/local-config", json={"draft": draft})
    confirmed = client.post("/api/profiles/demo-profile/local-config", json={"draft": draft, "confirmed": True})

    path = config_dir / "demo-profile.local.json"
    assert unconfirmed.status_code == 400
    assert confirmed.status_code == 200
    assert confirmed.json()["saved"] is True
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["profile"] == "demo-profile"
    assert payload["ga4"]["property_id_env"] == "DEMO_GA4_PROPERTY_ID"
    assert payload["google_ads_search"]["status"] == "planned"
    assert str(config_dir) not in json.dumps(confirmed.json())


def test_local_config_env_override_is_used_without_leaking_path_or_writing_default(tmp_path, monkeypatch):
    disposable_cwd = tmp_path / "repo-cwd"
    disposable_cwd.mkdir()
    monkeypatch.chdir(disposable_cwd)
    override_dir = tmp_path / "manual-qa-local-configs"
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR": str(override_dir)},
        )
    )
    draft = {
        "profile": "demo-profile",
        "ga4": {"property_id_env": "DEMO_GA4_PROPERTY_ID"},
        "gsc": {"site_url": "sc-domain:demo.example.test"},
        "local_falcon": {"manifest_path": "local-falcon-manifests/demo-profile.json"},
    }

    missing = client.get("/api/profiles/demo-profile/local-config/draft")
    preview = client.post("/api/profiles/demo-profile/local-config/preview", json={"draft": draft})

    override_file = override_dir / "demo-profile.local.json"
    default_relative_file = disposable_cwd / "local-profile-configs" / "demo-profile.local.json"
    assert missing.status_code == 200
    assert missing.json()["exists"] is False
    assert preview.status_code == 200
    assert not override_file.exists()

    saved = client.post("/api/profiles/demo-profile/local-config", json={"draft": draft, "confirmed": True})

    assert saved.status_code == 200
    assert override_file.exists()
    assert not default_relative_file.exists()
    serialized = json.dumps({"missing": missing.json(), "preview": preview.json(), "saved": saved.json()})
    assert str(override_dir) not in serialized
    assert "manual-qa-local-configs" not in serialized


def test_local_config_explicit_test_dir_takes_precedence_over_env_override(tmp_path):
    explicit_dir = tmp_path / "explicit-local-configs"
    ignored_override_dir = tmp_path / "ignored-local-configs"
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR": str(ignored_override_dir)},
            local_profile_config_dir=explicit_dir,
        )
    )
    draft = {
        "profile": "demo-profile",
        "ga4": {"property_id_env": "DEMO_GA4_PROPERTY_ID"},
    }

    response = client.post("/api/profiles/demo-profile/local-config", json={"draft": draft, "confirmed": True})

    assert response.status_code == 200
    assert (explicit_dir / "demo-profile.local.json").exists()
    assert not (ignored_override_dir / "demo-profile.local.json").exists()
    serialized = json.dumps(response.json())
    assert str(explicit_dir) not in serialized
    assert str(ignored_override_dir) not in serialized


def test_local_config_api_rejects_disallowed_and_secret_like_fields(tmp_path):
    config_dir = tmp_path / "local-profile-configs"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, local_profile_config_dir=config_dir))

    response = client.post(
        "/api/profiles/demo-profile/local-config/preview",
        json={
            "draft": {
                "profile": "demo-profile",
                "ga4": {
                    "property_id": "not-editable",
                    "property_id_env": "lowercase",
                    "oauth_client_secrets_env": '{"client_secret":"value"}',
                },
                "local_falcon": {"api_key_env": "LOCAL_FALCON_API_KEY_VALUE"},
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    assert payload["blocked"] is True
    assert "not editable" in serialized
    assert '{"client_secret":"value"}' not in serialized
    assert "lowercase" not in serialized
    assert not (config_dir / "demo-profile.local.json").exists()


def test_local_config_api_does_not_echo_dangerous_disallowed_field_names(tmp_path):
    config_dir = tmp_path / "local-profile-configs"
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, local_profile_config_dir=config_dir))

    response = client.post(
        "/api/profiles/demo-profile/local-config/preview",
        json={
            "draft": {
                "profile": "demo-profile",
                "ga4": {
                    '{"client_secret":"value"}': "DEMO_GA4_PROPERTY_ID",
                },
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    assert payload["blocked"] is True
    assert "not editable" in serialized
    assert '{"client_secret":"value"}' not in serialized
    assert not (config_dir / "demo-profile.local.json").exists()


def test_local_falcon_readiness_uses_env_key_when_vault_is_missing(tmp_path):
    registry = _registry(tmp_path)
    local_config = _local_falcon_config_without_key(tmp_path)
    vault_path = tmp_path / "missing-vault.local.json"
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "fake-local-falcon-api-key"},
            local_profile_config_path=local_config,
            secret_vault_path=vault_path,
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    local_falcon = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "local_falcon")
    assert local_falcon["config_state"]["api_key_visible"] is True
    assert local_falcon["config_state"]["api_key_env_present"] is True
    assert local_falcon["config_state"]["api_key_vault_configured"] is False
    assert local_falcon["credential_source"] == "Configured via env var"
    readiness = next(item for item in payload["provider_readiness"] if item["provider"] == "local_falcon")
    assert readiness["credentials_ready"] is True
    assert readiness["readiness"]["api_key_env_present"] is True
    assert readiness["readiness"]["api_key_vault_configured"] is False
    serialized = json.dumps(payload)
    assert "fake-local-falcon-api-key" not in serialized
    assert not vault_path.exists()


def test_local_falcon_readiness_prefers_env_when_env_and_vault_are_available(tmp_path):
    registry = _registry(tmp_path)
    local_config = _local_falcon_config_without_key(tmp_path)
    vault_path = tmp_path / "vault.local.json"
    fake_key = "fake-local-falcon-api-key"
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "fake-env-local-falcon-api-key"},
            local_profile_config_path=local_config,
            secret_vault_path=vault_path,
        )
    )
    client.post("/api/secrets/unlock", json={"passphrase": "fake test passphrase", "create_if_missing": True})
    client.post("/api/profiles/demo-profile/secrets/local_falcon/api_key", json={"value": fake_key})

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    local_falcon = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "local_falcon")
    assert local_falcon["credential_source"] == "Configured via env var"
    assert local_falcon["config_state"]["api_key_env_present"] is True
    assert local_falcon["config_state"]["api_key_vault_configured"] is False
    serialized = json.dumps(payload)
    assert "fake-env-local-falcon-api-key" not in serialized
    assert fake_key not in serialized
    assert "ciphertext" not in serialized
    assert str(vault_path) not in serialized


def test_local_falcon_readiness_uses_unlocked_vault_key_metadata(tmp_path):
    registry = _registry(tmp_path)
    local_config = _local_falcon_config_without_key(tmp_path)
    vault_path = tmp_path / "vault.local.json"
    fake_key = "fake-local-falcon-api-key"
    client = TestClient(
        create_app(registry_path=registry, env={}, local_profile_config_path=local_config, secret_vault_path=vault_path)
    )
    client.post("/api/secrets/unlock", json={"passphrase": "fake test passphrase", "create_if_missing": True})
    client.post("/api/profiles/demo-profile/secrets/local_falcon/api_key", json={"value": fake_key})

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    local_falcon = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "local_falcon")
    assert local_falcon["config_state"]["api_key_visible"] is True
    assert local_falcon["config_state"]["api_key_env_present"] is False
    assert local_falcon["config_state"]["api_key_vault_configured"] is True
    assert local_falcon["config_state"]["api_key_vault_locked"] is False
    assert local_falcon["credential_source"] == "Configured via vault"
    readiness = next(item for item in payload["provider_readiness"] if item["provider"] == "local_falcon")
    assert readiness["credentials_ready"] is True
    assert readiness["readiness"]["api_key_env_present"] is False
    assert readiness["readiness"]["api_key_vault_configured"] is True
    serialized = json.dumps(payload)
    assert fake_key not in serialized
    assert "ciphertext" not in serialized
    assert str(vault_path) not in serialized


def test_local_falcon_readiness_treats_locked_vault_as_needs_unlock_without_leaking_key(tmp_path):
    registry = _registry(tmp_path)
    local_config = _local_falcon_config_without_key(tmp_path)
    vault_path = tmp_path / "vault.local.json"
    fake_key = "fake-local-falcon-api-key"
    vault = LocalSecretVault.create(vault_path, passphrase="fake test passphrase")
    vault.set_secret(profile="demo-profile", provider="local_falcon", key="api_key", value=fake_key)
    vault.lock()
    client = TestClient(
        create_app(registry_path=registry, env={}, local_profile_config_path=local_config, secret_vault_path=vault_path)
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    local_falcon = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "local_falcon")
    assert local_falcon["config_state"]["api_key_visible"] is False
    assert local_falcon["config_state"]["api_key_vault_configured"] is False
    assert local_falcon["config_state"]["api_key_vault_locked"] is True
    assert local_falcon["credential_source"] == "Vault locked"
    assert "unlock vault" in json.dumps(local_falcon).lower()
    serialized = json.dumps(payload)
    assert fake_key not in serialized
    assert "ciphertext" not in serialized
    assert str(vault_path) not in serialized


def test_local_falcon_readiness_reports_missing_when_env_and_vault_are_missing(tmp_path):
    registry = _registry(tmp_path)
    local_config = _local_falcon_config_without_key(tmp_path)
    vault_path = tmp_path / "missing-vault.local.json"
    client = TestClient(
        create_app(registry_path=registry, env={}, local_profile_config_path=local_config, secret_vault_path=vault_path)
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    local_falcon = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "local_falcon")
    assert local_falcon["config_state"]["api_key_visible"] is False
    assert local_falcon["config_state"]["api_key_env_present"] is False
    assert local_falcon["config_state"]["api_key_vault_configured"] is False
    assert local_falcon["config_state"]["api_key_vault_locked"] is False
    assert local_falcon["credential_source"] == "Missing"
    assert "saved Local Falcon API key" in json.dumps(local_falcon)
    assert not vault_path.exists()


def test_local_falcon_readiness_handles_corrupt_temp_vault_safely(tmp_path):
    registry = _registry(tmp_path)
    local_config = _local_falcon_config_without_key(tmp_path)
    vault_path = tmp_path / "vault.local.json"
    vault_path.write_text("{raw corrupt vault contents", encoding="utf-8")
    client = TestClient(
        create_app(registry_path=registry, env={}, local_profile_config_path=local_config, secret_vault_path=vault_path)
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    local_falcon = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "local_falcon")
    assert local_falcon["credential_source"] == "Vault locked"
    assert local_falcon["config_state"]["api_key_visible"] is False
    serialized = json.dumps(payload)
    assert "raw corrupt vault contents" not in serialized
    assert str(vault_path) not in serialized


def test_non_local_falcon_profile_does_not_report_vault_key_readiness(tmp_path):
    registry = _registry(
        tmp_path,
        data_sources=["ga4", "gsc"],
        capabilities=[
            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
        ],
    )
    vault_path = tmp_path / "missing-vault.local.json"
    client = TestClient(create_app(registry_path=registry, env={}, secret_vault_path=vault_path))

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    assert all(item["provider_key"] != "local_falcon" for item in payload["provider_setup_checklist"])
    assert all(item.get("credential_source", "") == "" for item in payload["provider_setup_checklist"])
    assert not vault_path.exists()


def test_profiles_endpoint_returns_safe_profile_metadata(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profiles"][0]["slug"] == "demo-profile"
    assert payload["profiles"][0]["display_name"] == "Demo Profile"
    serialized = json.dumps(payload)
    assert "property-123" not in serialized
    assert "secret" not in serialized.lower()


def test_profile_detail_endpoint_includes_readiness_and_outputs_without_contents(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(profile_folder / "ga4-summary.json", {"schema_version": "ga4.v1", "private_metric": "do-not-return"})
    local_config = _local_profile_config(tmp_path)
    client = TestClient(
        create_app(
            registry_path=registry,
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "lf-secret-value",
            },
            local_profile_config_path=local_config,
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["slug"] == "demo-profile"
    assert payload["provider_readiness"][0]["label"] == "GA4"
    assert payload["readiness_matrix"][0]["provider_label"] == "GA4"
    assert payload["provider_setup_checklist"][0]["provider_label"] == "GA4"
    assert payload["output_status"]["files"][1]["file"] == "ga4-summary.json"
    assert payload["output_status"]["files"][1]["schema_version"] == "ga4.v1"
    serialized = json.dumps(payload)
    assert "do-not-return" not in serialized
    assert "property-123" not in serialized
    assert "C:/private" not in serialized
    assert "lf-secret-value" not in serialized


def test_onboarding_status_endpoint_returns_safe_read_only_matrix(tmp_path):
    registry = _registry(
        tmp_path,
        capabilities=[
            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
            {"key": "local_falcon", "label": "Local Falcon", "status": "enabled", "kind": "importer_provider", "provider": "local_falcon"},
            {"key": "google_ads_search", "label": "Google Ads Search", "status": "planned", "kind": "paid_provider"},
            {"key": "callrail", "label": "CallRail", "status": "planned", "kind": "lead_provider"},
            {"key": "form_fills", "label": "Form Fills", "status": "planned", "kind": "lead_provider"},
        ],
        data_sources=["ga4", "gsc", "local_falcon"],
    )
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(profile_folder / "ga4-summary.json", {"schema_version": "ga4.v1", "hidden": "do-not-return"})
    config_dir = tmp_path / "local-profile-configs"
    config_dir.mkdir()
    _write_json(
        config_dir / "demo-profile.local.json",
        {
            "profile": "demo-profile",
            "ga4": {
                "property_id_env": "QA_GA4_PROPERTY_ID",
                "oauth_client_secrets_env": "QA_GA4_CLIENT",
                "oauth_token_file_env": "QA_GA4_TOKEN",
            },
            "gsc": {
                "site_url": "sc-domain:example.com",
                "oauth_client_secrets_env": "QA_GSC_CLIENT",
                "oauth_token_file_env": "QA_GSC_TOKEN",
            },
            "local_falcon": {
                "manifest_path": "local-falcon-manifests/demo-profile.json",
                "api_key_env": "LOCAL_FALCON_API_KEY",
            },
        },
    )
    before_files = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())
    client = TestClient(
        create_app(
            registry_path=registry,
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
                "LOCAL_FALCON_API_KEY": "lf-secret-value",
            },
            local_profile_config_dir=config_dir,
            secret_vault_path=tmp_path / "vault.local.json",
        )
    )

    response = client.get("/api/profiles/demo-profile/onboarding-status")

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    providers = {item["provider"]: item for item in payload["providers"]}
    assert payload["profile"]["shell_state"] == "Profile shell created"
    assert payload["safety"] == {
        "read_only": True,
        "no_provider_execution": True,
        "no_fixture_copy": True,
        "no_secret_values": True,
        "no_file_contents": True,
    }
    assert providers["ga4"]["enabled"] is True
    assert providers["ga4"]["config_state"] == "Configured"
    assert providers["ga4"]["output_state"] == "Output exists"
    assert providers["gsc"]["enabled"] is True
    assert providers["local_falcon"]["enabled"] is True
    assert providers["google_ads_search"]["enabled"] is False
    assert providers["google_ads_search"]["config_state"] == "Not enabled"
    assert providers["callrail"]["output_state"] == "Not applicable"
    assert payload["local_config"]["state"] == "Configured"
    assert "demo-profile.local.json" in serialized
    assert "do-not-return" not in serialized
    assert "property-123" not in serialized
    assert "C:/private" not in serialized
    assert "lf-secret-value" not in serialized
    assert str(tmp_path) not in serialized
    after_files = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())
    assert after_files == before_files


def test_profile_detail_embeds_onboarding_status_without_raw_values(tmp_path):
    registry = _registry(tmp_path)
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload["onboarding_status"])
    assert payload["onboarding_status"]["providers"][0]["provider"] == "ga4"
    assert "real-api-key-value" not in serialized
    assert "configured_secret_value" not in serialized
    assert str(tmp_path) not in serialized


def test_profile_detail_setup_checklist_is_safe_and_profile_scoped(tmp_path):
    registry = _registry(tmp_path)
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    rows = response.json()["provider_setup_checklist"]
    local_falcon = next(item for item in rows if item["provider_key"] == "local_falcon")
    serialized = json.dumps(rows)
    assert local_falcon["profile_slug"] == "demo-profile"
    assert local_falcon["config_state"]["api_key_visible"] is True
    assert "local-falcon-manifests/demo-profile.json" in serialized
    assert "real-api-key-value" not in serialized
    assert "configured_secret_value" not in serialized
    assert "123456789" not in serialized
    assert "https://private-property.example.test/" not in serialized


def test_profile_detail_includes_planned_capabilities_without_fetch_actions(tmp_path):
    registry = _registry(
        tmp_path,
        capabilities=[
            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
            {"key": "google_ads_search", "label": "Google Ads Search", "status": "planned", "kind": "paid_provider"},
            {"key": "callrail", "label": "CallRail", "status": "planned", "kind": "lead_provider"},
        ],
        data_sources=["ga4", "gsc"],
    )
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    ads = next(item for item in payload["readiness_matrix"] if item["provider_key"] == "google_ads_search")
    callrail = next(item for item in payload["readiness_matrix"] if item["provider_key"] == "callrail")
    assert ads["status_label"] == "Planned, not enabled"
    assert ads["live_fetch_status"] == "Not available yet"
    assert callrail["dashboard_copy_readiness"] == "Not available yet"
    checklist_ads = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "google_ads_search")
    assert checklist_ads["suggested_command"] == ""
    assert checklist_ads["status"] == "planned"
    assert all(action["provider"] not in {"google_ads_search", "callrail"} for action in payload["action_plan"]["actions"])
    planned = _phase(payload["action_plan"]["guarded_import_sequence"], "planned_capabilities")["providers"]
    assert next(item for item in planned if item["provider"] == "google_ads_search")["command"] == ""
    assert next(item for item in planned if item["provider"] == "callrail")["command"] == ""


def test_profile_detail_includes_current_enabled_provider_files_and_actions(tmp_path):
    registry = _registry(
        tmp_path,
        capabilities=[
            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
            {"key": "local_falcon", "label": "Local Falcon", "status": "enabled", "kind": "importer_provider", "provider": "local_falcon"},
            {"key": "local_falcon_ai", "label": "Local Falcon AI Visibility", "status": "enabled", "kind": "dashboard_room", "notes": "Represented through local-falcon-summary.json"},
            {"key": "google_ads_search", "label": "Google Ads Search", "status": "enabled", "kind": "paid_provider", "provider": "google_ads_search", "expected_output_file": "google-ads-summary.json"},
            {"key": "callrail", "label": "CallRail", "status": "enabled", "kind": "lead_provider", "provider": "callrail", "expected_output_file": "callrail-summary.json"},
            {"key": "form_fills", "label": "Form Fills", "status": "enabled", "kind": "lead_provider", "provider": "form_fills", "expected_output_file": "form-fills-summary.json"},
        ],
        data_sources=["ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills"],
    )
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in (
        "client-profile.json",
        "combined-dashboard-summary.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "local-falcon-summary.json",
        "google-ads-summary.json",
        "callrail-summary.json",
        "form-fills-summary.json",
    ):
        _write_json(source / filename, {"schema_version": f"{filename}.v1", "hidden": "do-not-return"})
    _write_json(source / "ga4-snapshot.json", {"schema_version": "ga4_snapshot.v1", "hidden": "do-not-return"})
    client = TestClient(
        create_app(
            registry_path=registry,
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-secret",
                "GOOGLE_ADS_OAUTH_CLIENT_SECRETS": "C:/private/google-ads-client-secret.json",
                "GOOGLE_ADS_OAUTH_TOKEN_FILE": "C:/private/google-ads-token.json",
                "MUSIMACK_GOOGLE_ADS_CUSTOMER_ID": "9999999999",
                "LOCAL_FALCON_API_KEY": "local-falcon-secret",
            },
            local_profile_config_path=_full_provider_local_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile")
    preview = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 200
    assert preview.status_code == 200
    payload = response.json()
    expected_files = [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
        "local-falcon-summary.json",
        "google-ads-summary.json",
        "callrail-summary.json",
        "form-fills-summary.json",
    ]
    assert payload["output_status"]["expected_files"] == expected_files
    assert [item["file"] for item in preview.json()["items"]] == expected_files
    assert "ga4-snapshot.json" not in payload["output_status"]["expected_files"]
    assert "ga4-snapshot.json" not in [item["file"] for item in preview.json()["items"]]
    assert _action(payload["action_plan"], "google-ads-search-read-only-export")["provider"] == "google_ads_search"
    assert _action(payload["action_plan"], "callrail-csv-import")["provider"] == "callrail"
    assert _action(payload["action_plan"], "form-fills-date-only-import")["provider"] == "form_fills"
    serialized = json.dumps({"profile": payload, "preview": preview.json()})
    assert "do-not-return" not in serialized
    assert "property-123" not in serialized
    assert "9999999999" not in serialized
    assert "developer-token-secret" not in serialized
    assert "local-falcon-secret" not in serialized
    assert "C:/private" not in serialized
    assert "configured_secret_value" not in serialized


def test_unknown_profile_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/missing-profile")

    assert response.status_code == 404


def test_unknown_profile_action_plan_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/missing-profile/action-plan")

    assert response.status_code == 404


def test_unknown_profile_validation_action_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/missing-profile/actions/validate-output")

    assert response.status_code == 404


def test_unknown_profile_copy_preview_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/missing-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 404


def test_unknown_profile_copy_action_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/missing-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 404


def test_action_runs_missing_audit_log_returns_empty_list(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=tmp_path / "logs" / "missing.jsonl"))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    assert response.json() == {"entries": [], "count": 0, "skipped_malformed": 0}


def test_action_runs_endpoint_returns_recent_safe_entries(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(
        audit_path,
        {
            "timestamp": "2026-06-08T10:00:00+00:00",
            "action_id": "validate-output",
            "profile_slug": "demo-profile",
            "status": "ok",
            "result_summary": {"missing_required_file_count": 0, "raw_secret": "secret client payload"},
            "warnings": [],
            "duration_ms": 12,
            "raw_payload": "do-not-return",
        },
    )
    _write_audit(
        audit_path,
        {
            "timestamp": "2026-06-08T10:05:00+00:00",
            "action_id": "copy-to-dashboard-lab",
            "profile_slug": "demo-profile",
            "status": "ok",
            "file_counts": {"copied": 2, "skipped": 1, "failed": 0},
            "warnings": ["skipped missing source file(s): 1"],
            "duration_ms": 15,
        },
    )
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["entries"][0]["action_id"] == "copy-to-dashboard-lab"
    assert payload["entries"][0]["file_counts"]["copied"] == 2
    serialized = json.dumps(payload)
    assert "do-not-return" not in serialized
    assert "secret client payload" not in serialized
    assert "raw_payload" not in serialized


def test_action_runs_limit_and_filters_work(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(audit_path, {"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok"})
    _write_audit(audit_path, {"timestamp": "2", "action_id": "copy-to-dashboard-lab", "profile_slug": "other-profile", "status": "ok"})
    _write_audit(audit_path, {"timestamp": "3", "action_id": "copy-to-dashboard-lab", "profile_slug": "demo-profile", "status": "ok"})
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    limited = client.get("/api/action-runs?limit=1").json()
    filtered = client.get("/api/action-runs?profile_slug=demo-profile&action_id=copy-to-dashboard-lab").json()

    assert limited["count"] == 1
    assert limited["entries"][0]["timestamp"] == "3"
    assert filtered["count"] == 1
    assert filtered["entries"][0]["profile_slug"] == "demo-profile"
    assert filtered["entries"][0]["action_id"] == "copy-to-dashboard-lab"


def test_profile_action_runs_endpoint_filters_by_profile(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(audit_path, {"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok"})
    _write_audit(audit_path, {"timestamp": "2", "action_id": "validate-output", "profile_slug": "other-profile", "status": "ok"})
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/profiles/demo-profile/action-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["entries"][0]["profile_slug"] == "demo-profile"


def test_action_runs_malformed_jsonl_lines_are_skipped(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(
        "\n".join(
            [
                "{bad json",
                json.dumps({"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok"}),
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["skipped_malformed"] == 1


def test_action_runs_does_not_return_secrets(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(
        audit_path,
        {
            "timestamp": "1",
            "action_id": "validate-output",
            "profile_slug": "demo-profile",
            "status": "ok",
            "api_key": "real-api-key-value",
            "refresh_token": "refresh-secret",
            "warnings": ["safe warning"],
        },
    )
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "real-api-key-value" not in serialized
    assert "refresh-secret" not in serialized
    assert "safe warning" in serialized


def test_profile_detail_includes_last_action_summary_safely(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(audit_path, {"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok", "duration_ms": 9})
    _write_audit(audit_path, {"timestamp": "2", "action_id": "copy-to-dashboard-lab", "profile_slug": "demo-profile", "status": "ok", "file_counts": {"copied": 1}})
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    last_actions = response.json()["last_actions"]
    assert last_actions["last_action"]["action_id"] == "copy-to-dashboard-lab"
    assert last_actions["last_validation"]["action_id"] == "validate-output"
    assert last_actions["last_copy"]["file_counts"]["copied"] == 1


def test_action_runs_unknown_profile_filter_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/action-runs?profile_slug=missing-profile")

    assert response.status_code == 404


def test_outputs_endpoint_returns_status_only(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "client_value": "hidden"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/outputs")

    assert response.status_code == 200
    payload = response.json()
    assert [item["file"] for item in payload["files"]] == EXPECTED_DASHBOARD_FILES
    assert payload["files"][0]["exists"] is True
    assert "hidden" not in json.dumps(payload)


def test_local_config_and_secrets_are_not_exposed(tmp_path):
    local_config = _local_profile_config(tmp_path)
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            local_profile_config_path=local_config,
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "123456789" not in serialized
    assert "https://private-property.example.test/" not in serialized
    assert "real-api-key-value" not in serialized
    assert "configured_secret_value" not in serialized
    assert "credentials_ready" in serialized


def test_action_plan_endpoint_returns_safe_structured_data(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "lf-secret-value",
            },
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_slug"] == "demo-profile"
    assert [action["id"] for action in payload["actions"]] == [
        "ga4-snapshot",
        "gsc-fetch",
        "local-falcon-read-only-fetch",
        "validate-local-real-output",
        "copy-to-dashboard-lab-local-fixtures",
    ]
    assert "fetch_gsc_api.py --profile demo-profile" in json.dumps(payload)
    serialized = json.dumps(payload)
    assert "property-123" not in serialized
    assert "C:/private" not in serialized
    assert "lf-secret-value" not in serialized


def test_profile_detail_includes_guarded_import_sequence_without_secret_values(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "lf-secret-value",
            },
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    sequence = response.json()["guarded_import_sequence"]
    fetch_phase = _phase(sequence, "approved_provider_fetches")
    validation_phase = _phase(sequence, "validation_only")
    copy_phase = _phase(sequence, "dashboard_lab_local_copy")
    assert sequence["profile_slug"] == "demo-profile"
    assert fetch_phase["requires_explicit_approval"] is True
    assert fetch_phase["network_allowed"] is True
    assert validation_phase["network_allowed"] is False
    assert copy_phase["network_allowed"] is False
    assert "public/local-fixtures" in copy_phase["destination_folder"].replace("\\", "/")
    assert "public/fixtures" not in copy_phase["destination_folder"].replace("\\", "/")
    serialized = json.dumps(sequence)
    assert "property-123" not in serialized
    assert "C:/private" not in serialized
    assert "lf-secret-value" not in serialized
    assert "configured_secret_value" not in serialized


def test_action_plan_includes_same_guarded_import_sequence(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["guarded_import_sequence"]["profile_slug"] == "demo-profile"
    assert _phase(payload["guarded_import_sequence"], "validation_only")["network_allowed"] is False
    assert [action["id"] for action in payload["actions"]] == [
        "ga4-snapshot",
        "gsc-fetch",
        "local-falcon-read-only-fetch",
        "validate-local-real-output",
        "copy-to-dashboard-lab-local-fixtures",
    ]


def test_ga4_action_blocked_when_property_id_missing(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    action = _action(response.json(), "ga4-snapshot")
    assert action["status"] == "blocked_missing_config"
    assert any("MUSIMACK_GA4_PROPERTY_ID" in item for item in action["missing_inputs"])
    assert "ga4-summary.json writer is available" in " ".join(action["safety_notes"])
    assert action["readiness"]["dashboard_lab_writer_available"] is True


def test_local_falcon_action_checks_api_key_presence_without_exposing_value(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    action = _action(response.json(), "local-falcon-read-only-fetch")
    assert action["readiness"]["api_key_present"] is True
    assert "fetch_local_falcon_api.py" in action["command"]
    serialized = json.dumps(action)
    assert "LOCAL_FALCON_API_KEY" in serialized
    assert "real-api-key-value" not in serialized
    assert "configured_secret_value" not in serialized


def test_copy_action_targets_local_fixtures_not_committed_fixtures(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    action = _action(response.json(), "copy-to-dashboard-lab-local-fixtures")
    assert "public\\local-fixtures" in action["command"] or "public/local-fixtures" in action["command"]
    assert "public\\fixtures" not in action["command"]
    assert "public/fixtures" not in action["command"]
    assert action["readiness"]["destination_is_public_fixtures"] is False


def test_action_plan_does_not_return_raw_file_contents(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(profile_folder / "gsc-summary.json", {"schema_version": "gsc.v1", "raw_query": "secret client query"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    assert "secret client query" not in json.dumps(response.json())


def test_action_plan_avoids_secret_like_values_except_safe_env_var_names(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "real-api-key-value",
            },
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "real-api-key-value" not in serialized
    assert "C:/private" not in serialized
    assert "configured_secret_value" not in serialized
    assert "123456789" not in serialized
    assert "https://private-property.example.test/" not in serialized
    assert "LOCAL_FALCON_API_KEY" in serialized


def test_validation_action_succeeds_with_synthetic_output_folder(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "hidden": "do-not-return"})
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(create_app(registry_path=registry, env={}, audit_log_path=audit_path))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["result"]["folder_exists"] is True
    assert payload["result"]["missing_required_files"] == []
    assert all(item["exists"] for item in payload["result"]["files"])
    assert payload["audit"]["logged"] is True
    assert audit_path.exists()
    assert "do-not-return" not in json.dumps(payload)


def test_validation_action_folder_missing_returns_safe_status(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "folder_missing"
    assert payload["result"]["folder_exists"] is False
    assert "client-profile.json" in payload["result"]["missing_required_files"]


def test_validation_action_reports_missing_files(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(profile_folder / "client-profile.json", {"schema_version": "client.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "missing_outputs"
    assert "ga4-summary.json" in payload["result"]["missing_required_files"]
    assert "combined-dashboard-summary.json" in payload["result"]["missing_required_files"]


def test_validation_action_reports_malformed_json_without_crashing(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1"})
    (profile_folder / "gsc-summary.json").write_text("{bad json", encoding="utf-8")
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid_json"
    assert payload["result"]["malformed_json_files"] == ["gsc-summary.json"]


def test_validation_action_does_not_require_disabled_provider_file(tmp_path):
    registry = _registry(tmp_path, data_sources=["ga4", "gsc"])
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in (
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
    ):
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["result"]["missing_required_files"] == []
    assert payload["result"]["missing_disabled_provider_files"] == ["local-falcon-summary.json"]


def test_generic_action_allowlist_blocks_unsupported_action(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post(
        "/api/actions/run",
        json={"profile_slug": "demo-profile", "action_id": "gsc-fetch"},
    )

    assert response.status_code == 400


def test_generic_action_rejects_arbitrary_path_input(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post(
        "/api/actions/run",
        json={
            "profile_slug": "demo-profile",
            "action_id": "validate-output",
            "path": "C:/not-allowed",
        },
    )

    assert response.status_code == 422


def test_generic_action_can_run_validate_output(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post(
        "/api/actions/run",
        json={"profile_slug": "demo-profile", "action_id": "validate-output"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_validation_action_does_not_return_raw_file_contents(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "raw_value": "secret client payload"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    assert "secret client payload" not in json.dumps(response.json())


def test_validation_audit_log_writes_safe_jsonl_entry(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "raw_value": "secret client payload"})
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            audit_log_path=audit_path,
        )
    )

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action_id"] == "validate-output"
    assert entry["profile_slug"] == "demo-profile"
    assert entry["status"] == "ok"
    serialized = json.dumps(entry)
    assert "secret client payload" not in serialized
    assert "real-api-key-value" not in serialized


def test_copy_preview_returns_expected_file_actions(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    destination = tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
    _write_json(source / "client-profile.json", {"schema_version": "client.v1"})
    _write_json(source / "ga4-summary.json", {"schema_version": "ga4.v1"})
    _write_json(destination / "ga4-summary.json", {"schema_version": "old-ga4.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_folder"].endswith("exports\\local-real\\dashboard-lab\\demo-profile") or payload["source_folder"].endswith("exports/local-real/dashboard-lab/demo-profile")
    assert [item["file"] for item in payload["items"]] == EXPECTED_DASHBOARD_FILES
    assert _copy_item(payload, "client-profile.json")["action"] == "copy"
    assert _copy_item(payload, "ga4-summary.json")["action"] == "overwrite"
    assert _copy_item(payload, "gsc-summary.json")["action"] == "skip_missing_source"


def test_copy_action_requires_confirmation(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": False})

    assert response.status_code == 400


def test_copy_action_copies_only_expected_files_and_creates_destination(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    destination = tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(source / filename, {"schema_version": f"{filename}.v1", "payload": "safe"})
    (source / "raw-provider-response.json").write_text('{"raw": true}', encoding="utf-8")
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(create_app(registry_path=registry, env={}, audit_log_path=audit_path))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["counts"]["copied"] == len(EXPECTED_DASHBOARD_FILES)
    assert destination.exists()
    for filename in EXPECTED_DASHBOARD_FILES:
        assert (destination / filename).exists()
    assert not (destination / "raw-provider-response.json").exists()
    assert audit_path.exists()


def test_copy_action_reports_missing_sources_and_overwrites_existing(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    destination = tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
    _write_json(source / "client-profile.json", {"schema_version": "new-client.v1"})
    _write_json(destination / "client-profile.json", {"schema_version": "old-client.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    payload = response.json()
    assert _copy_item(payload, "client-profile.json")["status"] == "overwritten"
    assert _copy_item(payload, "ga4-summary.json")["status"] == "skipped_missing_source"
    assert payload["counts"]["skipped_missing_source"] == 4
    copied_payload = json.loads((destination / "client-profile.json").read_text(encoding="utf-8"))
    assert copied_payload["schema_version"] == "new-client.v1"


def test_copy_destination_committed_fixture_path_is_rejected(tmp_path):
    registry = _registry(tmp_path, local_fixture_folder=tmp_path / "musimack-dashboard-lab" / "public" / "fixtures" / "demo-profile")
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 500


def test_copy_source_outside_local_real_is_rejected(tmp_path):
    registry = _registry(tmp_path, importer_output_folder=tmp_path / "exports" / "not-local-real" / "demo-profile")
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 500


def test_copy_action_rejects_arbitrary_path_input(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post(
        "/api/profiles/demo-profile/actions/copy-to-dashboard-lab",
        json={"confirmed": True, "destination": "C:/not-allowed"},
    )

    assert response.status_code == 422


def test_generic_action_can_run_copy_to_dashboard_lab(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(source / filename, {"schema_version": f"{filename}.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post(
        "/api/actions/run",
        json={"profile_slug": "demo-profile", "action_id": "copy-to-dashboard-lab", "confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["counts"]["copied"] == len(EXPECTED_DASHBOARD_FILES)


def test_copy_audit_log_writes_safe_jsonl_entry(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(source / filename, {"schema_version": f"{filename}.v1", "raw_value": "secret client payload"})
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            audit_log_path=audit_path,
        )
    )

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    entry = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["action_id"] == "copy-to-dashboard-lab"
    assert entry["file_counts"]["copied"] == len(EXPECTED_DASHBOARD_FILES)
    serialized = json.dumps(entry)
    assert "secret client payload" not in serialized
    assert "real-api-key-value" not in serialized
    assert "raw_value" not in serialized


def test_copy_action_response_does_not_return_file_contents(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(source / "client-profile.json", {"schema_version": "client.v1", "raw_value": "secret client payload"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "secret client payload" not in serialized
    assert "raw_value" not in serialized


def test_copy_action_does_not_use_shell_or_subprocess():
    text = (Path(__file__).resolve().parents[1] / "server" / "main.py").read_text(encoding="utf-8")

    assert "import subprocess" not in text
    assert "subprocess." not in text
    assert "os.system" not in text
    assert "shell=True" not in text


def _new_profile_draft() -> dict:
    return {
        "slug": "new-client",
        "display_name": "New Client",
        "domain": "example.com",
        "vertical": "local service",
        "service_model": "SEO/GEO",
        "data_sources": ["ga4", "gsc", "local_falcon", "google_ads_search"],
        "capabilities": [
            {"key": "content", "status": "enabled"},
            {"key": "strategy", "status": "enabled"},
            {"key": "reports", "status": "enabled"},
            {"key": "support", "status": "enabled"},
            {"key": "operator_profile", "status": "enabled"},
            {"key": "local_falcon_ai", "status": "planned"},
        ],
    }


def _registry(
    tmp_path: Path,
    *,
    data_sources: list[str] | None = None,
    capabilities: list[dict] | None = None,
    importer_output_folder: Path | None = None,
    local_fixture_folder: Path | None = None,
) -> Path:
    registry = tmp_path / "profiles.json"
    registry.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "slug": "demo-profile",
                        "display_name": "Demo Profile",
                        "domain": "demo.example.test",
                        "vertical": "demo",
                        "service_model": "SEO/GEO",
                        "dashboard_lab_route": "/lab/demo-profile",
                        "importer_output_folder": str(importer_output_folder or (
                            tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
                        )),
                        "dashboard_lab_local_fixture_folder": str(local_fixture_folder or (
                            tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
                        )),
                        "dashboard_lab_synthetic_fixture_folder": str(
                            tmp_path / "musimack-dashboard-lab" / "public" / "fixtures" / "demo-profile"
                        ),
                        "data_sources": data_sources or ["ga4", "gsc", "local_falcon"],
                        "capabilities": capabilities or [
                            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
                            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
                            {"key": "local_falcon", "label": "Local Falcon", "status": "enabled", "kind": "importer_provider", "provider": "local_falcon"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return registry


def _local_profile_config(tmp_path: Path) -> Path:
    local_config = tmp_path / "dashboard_lab_profiles.local.json"
    local_config.write_text(
        json.dumps(
            {
                "profiles": {
                    "demo-profile": {
                        "providers": {
                            "ga4": {"property_id": "123456789", "credentials_configured": True},
                            "gsc": {"site_url": "https://private-property.example.test/", "credentials_configured": True},
                            "local_falcon": {
                                "manifest_path": str(tmp_path / "private-manifest.json"),
                                "api_key_present": True,
                                "private_note": "configured_secret_value",
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return local_config


def _local_falcon_config_without_key(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "private-manifest.json"
    _write_json(manifest_path, {"configured": "true"})
    local_config = tmp_path / "dashboard_lab_profiles.local.json"
    local_config.write_text(
        json.dumps(
            {
                "profiles": {
                    "demo-profile": {
                        "providers": {
                            "local_falcon": {
                                "manifest_path": str(manifest_path),
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return local_config


def _full_provider_local_config(tmp_path: Path) -> Path:
    local_config = tmp_path / "dashboard_lab_profiles.local.json"
    local_config.write_text(
        json.dumps(
            {
                "profiles": {
                    "demo-profile": {
                        "providers": {
                            "ga4": {"property_id": "123456789", "credentials_configured": True},
                            "gsc": {"site_url": "https://private-property.example.test/", "credentials_configured": True},
                            "local_falcon": {
                                "manifest_path": str(tmp_path / "private-manifest.json"),
                                "api_key_present": True,
                                "private_note": "configured_secret_value",
                            },
                            "google_ads_search": {
                                "customer_id": "9999999999",
                                "credentials_configured": True,
                                "oauth_client_secrets": "C:/private/google-ads-client-secret.json",
                                "oauth_token_file": "C:/private/google-ads-token.json",
                            },
                            "callrail": {
                                "input_csv": str(tmp_path / "private-callrail.csv"),
                            },
                            "form_fills": {
                                "input_csv": str(tmp_path / "private-form-fills.csv"),
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return local_config


def _write_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_audit(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _action(payload: dict, action_id: str) -> dict:
    return next(action for action in payload["actions"] if action["id"] == action_id)


def _copy_item(payload: dict, filename: str) -> dict:
    return next(item for item in payload["items"] if item["file"] == filename)


def _phase(sequence: dict, phase_id: str) -> dict:
    return next(item for item in sequence["phases"] if item["id"] == phase_id)
