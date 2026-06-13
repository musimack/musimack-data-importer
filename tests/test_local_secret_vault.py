from __future__ import annotations

import json

import pytest

from src.local_secret_vault import (
    CorruptVaultError,
    InvalidPassphraseError,
    InvalidSecretNameError,
    LocalSecretVault,
    MissingSecretError,
    VaultLockedError,
)


FAKE_PASSPHRASE = "fake local test passphrase"
FAKE_SECRET = "fake-secret-value-123"


def test_create_vault_with_temp_path(tmp_path):
    path = tmp_path / "vault.local.json"

    vault = LocalSecretVault.create(path, passphrase=FAKE_PASSPHRASE)

    assert path.exists()
    assert vault.locked is False
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "importer_secret_vault.v1"
    assert payload["kdf"]["name"] == "PBKDF2HMAC-SHA256"
    assert payload["entries"] == {}


def test_set_and_retrieve_secret_only_through_explicit_get(tmp_path):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)

    status = vault.set_secret(
        profile="wc-land-renewal",
        provider="local_falcon",
        key="api_key",
        value=FAKE_SECRET,
    )

    assert status.configured is True
    assert status.value_returned is False
    assert vault.get_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key") == FAKE_SECRET


def test_serialized_vault_does_not_contain_secret_or_passphrase(tmp_path):
    path = tmp_path / "vault.local.json"
    vault = LocalSecretVault.create(path, passphrase=FAKE_PASSPHRASE)
    vault.set_secret(
        profile="wc-land-renewal",
        provider="google_ads_search",
        key="developer_token",
        value=FAKE_SECRET,
    )

    serialized = path.read_text(encoding="utf-8")

    assert FAKE_SECRET not in serialized
    assert FAKE_PASSPHRASE not in serialized
    assert "developer_token" in serialized
    assert "ciphertext" in serialized


def test_status_output_does_not_contain_secret_value(tmp_path):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)
    vault.set_secret(
        profile="wc-land-renewal",
        provider="local_falcon",
        key="api_key",
        value=FAKE_SECRET,
    )

    safe_payload = json.dumps(
        {
            "status": vault.status(profile="wc-land-renewal", provider="local_falcon", key="api_key").as_safe_dict(),
            "list": [item.as_safe_dict() for item in vault.list_status()],
            "vault": vault.as_safe_dict(),
        },
        sort_keys=True,
    )

    assert FAKE_SECRET not in safe_payload
    assert FAKE_PASSPHRASE not in safe_payload
    assert '"value_returned": false' in safe_payload


def test_status_output_does_not_contain_ciphertext(tmp_path):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)
    vault.set_secret(
        profile="wc-land-renewal",
        provider="local_falcon",
        key="api_key",
        value=FAKE_SECRET,
    )

    safe_payload = json.dumps(
        {
            "status": vault.status(profile="wc-land-renewal", provider="local_falcon", key="api_key").as_safe_dict(),
            "list": [item.as_safe_dict() for item in vault.list_status()],
            "vault": vault.as_safe_dict(),
        },
        sort_keys=True,
    )

    assert "ciphertext" not in safe_payload


def test_wrong_passphrase_fails(tmp_path):
    path = tmp_path / "vault.local.json"
    LocalSecretVault.create(path, passphrase=FAKE_PASSPHRASE)
    vault = LocalSecretVault.load(path)

    with pytest.raises(InvalidPassphraseError):
        vault.unlock("wrong passphrase")


def test_lock_prevents_secret_retrieval(tmp_path):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)
    vault.set_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key", value=FAKE_SECRET)

    vault.lock()

    with pytest.raises(VaultLockedError):
        vault.get_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key")


def test_unlock_restores_retrieval(tmp_path):
    path = tmp_path / "vault.local.json"
    vault = LocalSecretVault.create(path, passphrase=FAKE_PASSPHRASE)
    vault.set_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key", value=FAKE_SECRET)
    vault.lock()

    vault.unlock(FAKE_PASSPHRASE)

    assert vault.get_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key") == FAKE_SECRET


def test_load_existing_vault_then_unlock(tmp_path):
    path = tmp_path / "vault.local.json"
    vault = LocalSecretVault.create(path, passphrase=FAKE_PASSPHRASE)
    vault.set_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key", value=FAKE_SECRET)

    loaded = LocalSecretVault.load(path)

    assert loaded.locked is True
    loaded.unlock(FAKE_PASSPHRASE)
    assert loaded.get_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key") == FAKE_SECRET


def test_update_changes_value_and_updated_timestamp(tmp_path):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)
    first = vault.set_secret(
        profile="wc-land-renewal",
        provider="google_ads_search",
        key="developer_token",
        value="first-fake-secret",
    )

    second = vault.set_secret(
        profile="wc-land-renewal",
        provider="google_ads_search",
        key="developer_token",
        value="second-fake-secret",
    )

    assert vault.get_secret(profile="wc-land-renewal", provider="google_ads_search", key="developer_token") == "second-fake-secret"
    assert second.created_at == first.created_at
    assert second.updated_at > first.updated_at


def test_delete_removes_entry_and_prevents_retrieval(tmp_path):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)
    vault.set_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key", value=FAKE_SECRET)

    status = vault.delete_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key")

    assert status.configured is False
    with pytest.raises(MissingSecretError):
        vault.get_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key")


def test_multiple_entries_remain_separate(tmp_path):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)
    vault.set_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key", value="wc-lf")
    vault.set_secret(profile="wc-land-renewal", provider="google_ads_search", key="developer_token", value="wc-ads")
    vault.set_secret(profile="inn-at-spanish-head", provider="local_falcon", key="api_key", value="spanish-lf")

    assert vault.get_secret(profile="wc-land-renewal", provider="local_falcon", key="api_key") == "wc-lf"
    assert vault.get_secret(profile="wc-land-renewal", provider="google_ads_search", key="developer_token") == "wc-ads"
    assert vault.get_secret(profile="inn-at-spanish-head", provider="local_falcon", key="api_key") == "spanish-lf"
    assert len(vault.list_status()) == 3


@pytest.mark.parametrize(
    ("profile", "provider", "key"),
    [
        ("../wc", "local_falcon", "api_key"),
        ("wc-land-renewal", "LocalFalcon", "api_key"),
        ("wc-land-renewal", "local_falcon", "api key"),
    ],
)
def test_invalid_profile_provider_or_key_names_are_rejected(tmp_path, profile, provider, key):
    vault = LocalSecretVault.create(tmp_path / "vault.local.json", passphrase=FAKE_PASSPHRASE)

    with pytest.raises(InvalidSecretNameError):
        vault.set_secret(profile=profile, provider=provider, key=key, value=FAKE_SECRET)


def test_corrupt_vault_file_raises_controlled_error(tmp_path):
    path = tmp_path / "vault.local.json"
    path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(CorruptVaultError):
        LocalSecretVault.load(path)


def test_corrupt_vault_schema_raises_controlled_error(tmp_path):
    path = tmp_path / "vault.local.json"
    path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    with pytest.raises(CorruptVaultError):
        LocalSecretVault.load(path)


def test_corrupt_vault_salt_raises_controlled_error(tmp_path):
    path = tmp_path / "vault.local.json"
    vault = LocalSecretVault.create(path, passphrase=FAKE_PASSPHRASE)
    vault.lock()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["kdf"]["salt"] = "not valid base64!"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorruptVaultError):
        LocalSecretVault.load(path)
