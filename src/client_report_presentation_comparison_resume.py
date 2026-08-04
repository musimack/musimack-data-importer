"""Durable preset-level resume for the R4 presentation comparison stage.

The comparison stage issues 216 sequential provider requests across 12 canonical
presets. Long-lived sessions were observed being reset by the remote host
partway through a burst (`R8C5-COMPARISON-TRANSPORT-01`), and because the stage
had no durable state, every failure discarded up to 216 already-paid requests.

This module adds the missing durability and nothing else. It does not retry, it
does not re-issue, and it does not decide when to run. A failed provider request
still stops the run immediately; restarting the command remains an explicit
operator action. The only behavior that changes is that presets already paid for
are not paid for twice.

Safety properties, all enforced here rather than asserted in documentation:

* A preset record is written only after the entire preset succeeded.
* Writes are atomic: a temporary file is flushed, fsynced, and renamed.
* Every record is bound to the exact run identity. Any mismatch refuses resume
  rather than silently producing a blended artifact.
* Corrupt, duplicate, unknown, or conflicting state refuses resume.
* Partial state carries a checkpoint schema identifier, never the final
  comparison contract identifier, so it cannot be mistaken for a final artifact.
* Partial state is secret-scanned on write, exactly as the final artifact is.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.client_report_presentation_comparisons import (
    COMPARISON_CONTRACT_VERSION,
    COMPARISON_DATASET_VERSION,
    COMPARISON_PRESET_KEYS,
    COMPARISON_SCHEMA_VERSION,
)


CHECKPOINT_SCHEMA_VERSION = "client_report_presentation_comparison_checkpoint.v1"
# Bumped whenever the comparison retrieval semantics change in a way that makes
# a previously completed preset no longer equivalent to a freshly built one.
# Records carrying a different value refuse resume.
COMPARISON_OPERATION_VERSION = "bounded_provider_exact_ranges.v1"

IDENTITY_FILENAME = "identity.json"
_TEMP_PREFIX = ".tmp-"

# Measured against the real generator, not derived by reading the loop: each
# preset yields ga4_top_metrics, ga4_user_engagement, ga4_website_traffic_trends,
# four GA4 ranked families, and three GSC families.
ENTRIES_PER_PRESET = 10
EXPECTED_TOTAL_ENTRIES = ENTRIES_PER_PRESET * len(COMPARISON_PRESET_KEYS)

_PRESET_INDEX = {key: index for index, key in enumerate(COMPARISON_PRESET_KEYS)}

# Scanned for on every artifact this stage writes, partial and final alike.
FORBIDDEN_SECRET_TERMS = (
    "access_token",
    "refresh_token",
    "private_key",
    "client_secret",
    "authorization",
    "bearer ",
    "api_key",
    "apikey",
    "oauth_token",
    "x-goog-api-key",
)


class ComparisonResumeError(RuntimeError):
    """Raised when partial state cannot be trusted, so resume is refused."""


def assert_no_secret_material(payload: Any, *, label: str) -> None:
    """Refuse to write an artifact that contains secret-shaped material.

    Applied to partial checkpoint records and to the final comparison contract,
    so durability cannot become a new disclosure path.
    """
    text = json.dumps(payload, sort_keys=True, default=str).lower()
    for term in FORBIDDEN_SECRET_TERMS:
        if term in text:
            raise ComparisonResumeError(
                f"{label} contains forbidden secret-shaped material: {term!r}"
            )


def provider_configuration_fingerprint(*, ga4_property_id: str, gsc_site_url: str) -> str:
    """Bind partial state to the provider configuration without disclosing it.

    The property id and site URL are provider identifiers that this stage is
    forbidden to write. Hashing them still refuses a resume that would blend
    two differently configured runs.
    """
    material = f"ga4_property={ga4_property_id}\x1fgsc_site={gsc_site_url}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ComparisonRunIdentity:
    """The exact identity a completed preset is bound to.

    Any difference in any field refuses resume. Period, dataset, contract
    version, and comparison operation version are all part of the binding, so a
    record cannot survive a semantic change to the stage that produced it.
    """

    profile: str
    report_id: str
    client_id: str
    project_id: str
    report_start: date
    report_end: date
    gsc_available_through: date
    provider_configuration_fingerprint: str

    def manifest(self) -> dict[str, Any]:
        return {
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "profile": self.profile,
            "report_id": self.report_id,
            "client_id": self.client_id,
            "project_id": self.project_id,
            "report_period": {
                "start_date": self.report_start.isoformat(),
                "end_date": self.report_end.isoformat(),
            },
            "gsc_available_through_date": self.gsc_available_through.isoformat(),
            "dataset_identity": (
                f"{self.profile}:{self.report_id}:{self.report_end.isoformat()}:"
                f"{COMPARISON_DATASET_VERSION}"
            ),
            "provider_configuration_fingerprint": self.provider_configuration_fingerprint,
            "contract_identifier": COMPARISON_SCHEMA_VERSION,
            "contract_version": COMPARISON_CONTRACT_VERSION,
            "comparison_operation_version": COMPARISON_OPERATION_VERSION,
            "preset_order": list(COMPARISON_PRESET_KEYS),
        }

    def fingerprint(self) -> str:
        return _digest(self.manifest())


@dataclass(frozen=True)
class CompletedPreset:
    preset_key: str
    entries: list[dict[str, Any]]
    ga4_calls: int
    gsc_calls: int


class ComparisonCheckpointStore:
    """Durable, atomically written, identity-bound preset state.

    Disabled stores (`directory=None`) are legal and behave exactly as the
    stage did before resume existed, so the unresumed path stays available.
    """

    def __init__(self, directory: Path | None, identity: ComparisonRunIdentity) -> None:
        self._directory = Path(directory).resolve(strict=False) if directory is not None else None
        self._identity = identity
        self._fingerprint = identity.fingerprint()
        self._written: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self._directory is not None

    @property
    def directory(self) -> Path | None:
        return self._directory

    def _preset_path(self, preset_key: str) -> Path:
        assert self._directory is not None
        return self._directory / f"preset-{_PRESET_INDEX[preset_key]:02d}-{preset_key}.json"

    def load(self) -> dict[str, CompletedPreset]:
        """Return validated completed presets, or refuse resume.

        Returns an empty mapping for a store that has never been written. Every
        other unexpected condition is an error: silently discarding unreadable
        state would re-spend requests, and silently accepting it would produce
        an artifact that is not equivalent to a clean run.
        """
        if self._directory is None or not self._directory.exists():
            return {}

        entries = sorted(
            path for path in self._directory.iterdir() if path.is_file()
        )
        stray = [
            path.name
            for path in entries
            if path.name != IDENTITY_FILENAME
            and not path.name.startswith(_TEMP_PREFIX)
            and not _is_preset_filename(path.name)
        ]
        if stray:
            raise ComparisonResumeError(
                f"comparison checkpoint directory holds unknown state: {', '.join(sorted(stray))}"
            )

        preset_files = [path for path in entries if _is_preset_filename(path.name)]
        identity_path = self._directory / IDENTITY_FILENAME
        if not identity_path.exists():
            if not preset_files:
                return {}
            raise ComparisonResumeError(
                "comparison checkpoint holds preset state with no identity manifest"
            )

        stored_identity = _read_json(identity_path, "comparison checkpoint identity manifest")
        if _digest(stored_identity) != self._fingerprint:
            raise ComparisonResumeError(
                "comparison checkpoint identity does not match this run. Resume is "
                "refused. Profile, report, client, project, period, dataset "
                "identity, provider configuration, contract version, and "
                "comparison operation version must all match exactly."
            )

        completed: dict[str, CompletedPreset] = {}
        for path in preset_files:
            record = _read_json(path, f"comparison checkpoint record {path.name}")
            preset_key = _validate_record(
                record,
                path=path,
                expected_fingerprint=self._fingerprint,
            )
            if preset_key in completed:
                raise ComparisonResumeError(
                    f"comparison checkpoint holds duplicate state for preset {preset_key}"
                )
            completed[preset_key] = CompletedPreset(
                preset_key=preset_key,
                entries=record["entries"],
                ga4_calls=int(record["ga4_provider_calls"]),
                gsc_calls=int(record["gsc_provider_calls"]),
            )
        return completed

    def record(
        self,
        *,
        preset_key: str,
        entries: list[dict[str, Any]],
        ga4_calls: int,
        gsc_calls: int,
    ) -> None:
        """Persist one fully completed preset atomically.

        Called only after the entire preset succeeded. A preset that failed
        partway is never recorded, so it is rebuilt in full on the next run.
        """
        if self._directory is None:
            return
        if preset_key not in _PRESET_INDEX:
            raise ComparisonResumeError(f"unknown comparison preset: {preset_key}")
        if len(entries) != ENTRIES_PER_PRESET:
            raise ComparisonResumeError(
                f"preset {preset_key} produced {len(entries)} comparison entries, "
                f"expected {ENTRIES_PER_PRESET}; refusing to record it as complete"
            )
        if any(entry.get("preset_key") != preset_key for entry in entries):
            raise ComparisonResumeError(
                f"preset {preset_key} produced entries belonging to another preset"
            )
        if preset_key in self._written:
            raise ComparisonResumeError(
                f"preset {preset_key} was already recorded in this run"
            )

        payload = {
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "identity_fingerprint": self._fingerprint,
            "preset_key": preset_key,
            "preset_index": _PRESET_INDEX[preset_key],
            "ga4_provider_calls": int(ga4_calls),
            "gsc_provider_calls": int(gsc_calls),
            "entries_digest": _digest(entries),
            "entries": entries,
        }
        assert_no_secret_material(payload, label=f"comparison checkpoint record {preset_key}")
        self._directory.mkdir(parents=True, exist_ok=True)
        identity_path = self._directory / IDENTITY_FILENAME
        if not identity_path.exists():
            _atomic_write_json(identity_path, self._identity.manifest())
        _atomic_write_json(self._preset_path(preset_key), payload)
        self._written.add(preset_key)


def _is_preset_filename(name: str) -> bool:
    return any(
        name == f"preset-{index:02d}-{key}.json" for key, index in _PRESET_INDEX.items()
    )


def _preset_key_for_filename(name: str) -> str:
    for key, index in _PRESET_INDEX.items():
        if name == f"preset-{index:02d}-{key}.json":
            return key
    raise ComparisonResumeError(f"unknown comparison checkpoint filename: {name}")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ComparisonResumeError(f"{label} is unreadable or corrupt: {exc}") from exc


def _validate_record(record: Any, *, path: Path, expected_fingerprint: str) -> str:
    label = f"comparison checkpoint record {path.name}"
    if not isinstance(record, dict):
        raise ComparisonResumeError(f"{label} is not an object")
    if record.get("checkpoint_schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise ComparisonResumeError(f"{label} carries an unsupported checkpoint schema")
    if record.get("identity_fingerprint") != expected_fingerprint:
        raise ComparisonResumeError(
            f"{label} was produced under a different run identity. Resume is refused."
        )
    preset_key = record.get("preset_key")
    if preset_key not in _PRESET_INDEX:
        raise ComparisonResumeError(f"{label} names an unknown preset: {preset_key!r}")
    if preset_key != _preset_key_for_filename(path.name):
        raise ComparisonResumeError(
            f"{label} names preset {preset_key!r}, which conflicts with its filename"
        )
    if record.get("preset_index") != _PRESET_INDEX[preset_key]:
        raise ComparisonResumeError(f"{label} carries a conflicting preset index")

    entries = record.get("entries")
    if not isinstance(entries, list) or len(entries) != ENTRIES_PER_PRESET:
        raise ComparisonResumeError(
            f"{label} does not hold exactly {ENTRIES_PER_PRESET} comparison entries"
        )
    if any(not isinstance(entry, dict) or entry.get("preset_key") != preset_key for entry in entries):
        raise ComparisonResumeError(f"{label} holds entries belonging to another preset")
    if record.get("entries_digest") != _digest(entries):
        raise ComparisonResumeError(f"{label} failed its integrity digest; state is corrupt")

    for field in ("ga4_provider_calls", "gsc_provider_calls"):
        value = record.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ComparisonResumeError(f"{label} carries an invalid {field}")
    return preset_key


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON so a crash mid-write cannot leave a partially written record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=_TEMP_PREFIX,
        suffix=".json",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
