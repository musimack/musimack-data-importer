from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from os import urandom


DEFAULT_VAULT_PATH = Path("secrets") / "importer-vault.local.json"
SCHEMA_VERSION = "importer_secret_vault.v1"
KDF_NAME = "PBKDF2HMAC-SHA256"
KDF_ITERATIONS = 390_000
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
CLASSIFICATION_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
VERIFIER_TEXT = "importer-secret-vault"


class LocalSecretVaultError(ValueError):
    pass


class VaultLockedError(LocalSecretVaultError):
    pass


class InvalidPassphraseError(LocalSecretVaultError):
    pass


class MissingSecretError(LocalSecretVaultError):
    pass


class InvalidSecretNameError(LocalSecretVaultError):
    pass


class CorruptVaultError(LocalSecretVaultError):
    pass


@dataclass(frozen=True)
class SecretStatus:
    configured: bool
    profile: str
    provider: str
    key: str
    classification: str = ""
    source: str = "vault"
    created_at: str = ""
    updated_at: str = ""
    value_returned: bool = False

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "profile": self.profile,
            "provider": self.provider,
            "key": self.key,
            "classification": self.classification,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "value_returned": False,
        }


class LocalSecretVault:
    def __init__(self, path: Path, payload: dict[str, Any]) -> None:
        self.path = path
        self._payload = payload
        self._fernet: Fernet | None = None

    @classmethod
    def create(cls, path: Path = DEFAULT_VAULT_PATH, *, passphrase: str) -> "LocalSecretVault":
        _validate_passphrase(passphrase)
        salt = urandom(16)
        fernet = _fernet_from_passphrase(passphrase, salt, KDF_ITERATIONS)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kdf": {
                "name": KDF_NAME,
                "salt": _b64encode(salt),
                "iterations": KDF_ITERATIONS,
            },
            "verifier": fernet.encrypt(VERIFIER_TEXT.encode("utf-8")).decode("ascii"),
            "entries": {},
        }
        vault = cls(path, payload)
        vault._fernet = fernet
        vault._write()
        return vault

    @classmethod
    def load(cls, path: Path = DEFAULT_VAULT_PATH) -> "LocalSecretVault":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptVaultError("vault file is not valid JSON") from exc
        except OSError as exc:
            raise CorruptVaultError("vault file could not be read") from exc
        _validate_payload(payload)
        return cls(path, payload)

    @property
    def locked(self) -> bool:
        return self._fernet is None

    def unlock(self, passphrase: str) -> None:
        _validate_passphrase(passphrase)
        salt = _salt_from_payload(self._payload)
        iterations = _iterations_from_payload(self._payload)
        fernet = _fernet_from_passphrase(passphrase, salt, iterations)
        try:
            verifier = fernet.decrypt(str(self._payload["verifier"]).encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise InvalidPassphraseError("vault passphrase is invalid") from exc
        if verifier != VERIFIER_TEXT:
            raise InvalidPassphraseError("vault passphrase is invalid")
        self._fernet = fernet

    def lock(self) -> None:
        self._fernet = None

    def set_secret(
        self,
        *,
        profile: str,
        provider: str,
        key: str,
        value: str,
        classification: str = "secret",
    ) -> SecretStatus:
        self._require_unlocked()
        _validate_entry_names(profile=profile, provider=provider, key=key, classification=classification)
        text_value = str(value)
        entry_id = _entry_id(profile, provider, key)
        now = _utc_now()
        existing = self._entries().get(entry_id)
        created_at = str(existing.get("created_at")) if isinstance(existing, dict) and existing.get("created_at") else now
        updated_at = _later_timestamp(now, str(existing.get("updated_at", ""))) if isinstance(existing, dict) else now
        ciphertext = self._fernet.encrypt(text_value.encode("utf-8")).decode("ascii")  # type: ignore[union-attr]
        self._entries()[entry_id] = {
            "profile": profile,
            "provider": provider,
            "key": key,
            "classification": classification,
            "source": "vault",
            "created_at": created_at,
            "updated_at": updated_at,
            "ciphertext": ciphertext,
        }
        self._write()
        return self.status(profile=profile, provider=provider, key=key)

    def get_secret(self, *, profile: str, provider: str, key: str) -> str:
        self._require_unlocked()
        _validate_entry_names(profile=profile, provider=provider, key=key)
        entry = self._entry(profile=profile, provider=provider, key=key)
        try:
            return self._fernet.decrypt(str(entry["ciphertext"]).encode("ascii")).decode("utf-8")  # type: ignore[union-attr]
        except (InvalidToken, ValueError, KeyError) as exc:
            raise CorruptVaultError("vault entry could not be decrypted") from exc

    def delete_secret(self, *, profile: str, provider: str, key: str) -> SecretStatus:
        self._require_unlocked()
        _validate_entry_names(profile=profile, provider=provider, key=key)
        entry_id = _entry_id(profile, provider, key)
        if entry_id not in self._entries():
            raise MissingSecretError("secret entry is missing")
        del self._entries()[entry_id]
        self._write()
        return self.status(profile=profile, provider=provider, key=key)

    def status(self, *, profile: str, provider: str, key: str) -> SecretStatus:
        _validate_entry_names(profile=profile, provider=provider, key=key)
        entry = self._entries().get(_entry_id(profile, provider, key))
        if not isinstance(entry, dict):
            return SecretStatus(configured=False, profile=profile, provider=provider, key=key)
        return _status_from_entry(entry)

    def list_status(self) -> list[SecretStatus]:
        statuses = []
        for entry in self._entries().values():
            if not isinstance(entry, dict):
                raise CorruptVaultError("vault contains an invalid entry")
            statuses.append(_status_from_entry(entry))
        return sorted(statuses, key=lambda item: (item.profile, item.provider, item.key))

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "path": self.path.as_posix(),
            "schema_version": self._payload.get("schema_version", ""),
            "locked": self.locked,
            "entries": [status.as_safe_dict() for status in self.list_status()],
        }

    def _entry(self, *, profile: str, provider: str, key: str) -> dict[str, Any]:
        entry = self._entries().get(_entry_id(profile, provider, key))
        if not isinstance(entry, dict):
            raise MissingSecretError("secret entry is missing")
        return entry

    def _entries(self) -> dict[str, Any]:
        entries = self._payload.get("entries")
        if not isinstance(entries, dict):
            raise CorruptVaultError("vault entries must be a JSON object")
        return entries

    def _require_unlocked(self) -> None:
        if self._fernet is None:
            raise VaultLockedError("vault is locked")

    def _write(self) -> None:
        _validate_payload(self._payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f".{self.path.name}.tmp")
        text = json.dumps(self._payload, indent=2, sort_keys=True) + "\n"
        try:
            temp_path.write_text(text, encoding="utf-8")
            temp_path.replace(self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def _status_from_entry(entry: dict[str, Any]) -> SecretStatus:
    return SecretStatus(
        configured=True,
        profile=str(entry.get("profile", "")),
        provider=str(entry.get("provider", "")),
        key=str(entry.get("key", "")),
        classification=str(entry.get("classification", "")),
        source=str(entry.get("source", "vault")),
        created_at=str(entry.get("created_at", "")),
        updated_at=str(entry.get("updated_at", "")),
    )


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise CorruptVaultError("vault file must contain a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise CorruptVaultError("vault schema version is unsupported")
    kdf = payload.get("kdf")
    if not isinstance(kdf, dict):
        raise CorruptVaultError("vault kdf metadata is missing")
    if kdf.get("name") != KDF_NAME:
        raise CorruptVaultError("vault kdf is unsupported")
    _salt_from_payload(payload)
    _iterations_from_payload(payload)
    if not isinstance(payload.get("verifier"), str) or not payload.get("verifier"):
        raise CorruptVaultError("vault verifier is missing")
    if not isinstance(payload.get("entries"), dict):
        raise CorruptVaultError("vault entries must be a JSON object")
    for entry in payload["entries"].values():
        _validate_entry_payload(entry)


def _validate_entry_payload(entry: Any) -> None:
    if not isinstance(entry, dict):
        raise CorruptVaultError("vault contains an invalid entry")
    _validate_entry_names(
        profile=str(entry.get("profile", "")),
        provider=str(entry.get("provider", "")),
        key=str(entry.get("key", "")),
        classification=str(entry.get("classification", "")),
    )
    if entry.get("source") != "vault":
        raise CorruptVaultError("vault entry source is unsupported")
    if not isinstance(entry.get("ciphertext"), str) or not entry.get("ciphertext"):
        raise CorruptVaultError("vault entry ciphertext is missing")


def _validate_entry_names(*, profile: str, provider: str, key: str, classification: str = "secret") -> None:
    for label, value in (("profile", profile), ("provider", provider), ("key", key)):
        if not NAME_RE.match(value):
            raise InvalidSecretNameError(f"{label} must contain only lowercase letters, numbers, hyphens, or underscores")
    if not CLASSIFICATION_RE.match(classification):
        raise InvalidSecretNameError("classification must contain only lowercase letters, numbers, or underscores")


def _validate_passphrase(passphrase: str) -> None:
    if not str(passphrase):
        raise InvalidPassphraseError("vault passphrase is required")


def _fernet_from_passphrase(passphrase: str, salt: bytes, iterations: int) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    return Fernet(key)


def _salt_from_payload(payload: dict[str, Any]) -> bytes:
    try:
        salt_text = str(payload["kdf"]["salt"])
        salt = _b64decode(salt_text)
    except (binascii.Error, KeyError, ValueError) as exc:
        raise CorruptVaultError("vault salt is invalid") from exc
    if len(salt) < 16:
        raise CorruptVaultError("vault salt is too short")
    return salt


def _iterations_from_payload(payload: dict[str, Any]) -> int:
    try:
        iterations = int(payload["kdf"]["iterations"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CorruptVaultError("vault kdf iterations are invalid") from exc
    if iterations < 100_000:
        raise CorruptVaultError("vault kdf iterations are too low")
    return iterations


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _entry_id(profile: str, provider: str, key: str) -> str:
    return f"{profile}:{provider}:{key}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _later_timestamp(candidate: str, previous: str) -> str:
    if not previous or candidate > previous:
        return candidate
    try:
        previous_datetime = datetime.fromisoformat(previous.replace("Z", "+00:00"))
    except ValueError:
        return candidate
    return (previous_datetime + timedelta(microseconds=1)).isoformat(timespec="microseconds").replace("+00:00", "Z")
