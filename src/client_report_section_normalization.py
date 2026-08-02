"""Canonical section-key normalization for newly generated handoffs.

The portal normalizes accepted legacy alias keys at its import boundary and
records provenance under ``data_json.import_provenance``. That correction is
defensive and stays in force: the portal must not trust importer output.

This module closes the same gap one step earlier, so a *newly generated*
handoff carries canonical stored keys from the moment it is written, and the
portal's normalization becomes a no-op for it rather than the only line of
defense.

Three rules, matching the portal exactly:

- Only the three accepted legacy aliases are resolved. Nothing is inferred from
  labels and there is no fuzzy matching.
- Keys that resolve to no canonical identity are left exactly as supplied.
  Normalization changes spelling, never what counts as a canonical section.
- Two source keys resolving to one canonical identity **reject the whole
  handoff**. Nothing is merged, deduplicated, or dropped.

Provenance is truthful about lifecycle stage. It records what the *importer*
emitted, and deliberately does not claim that a portal import has occurred.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from src.client_report_publisher_contracts import (
    canonical_section_key,
    detect_canonical_section_collisions,
)

NORMALIZATION_CONTRACT = "musimack_canonical_section_key_normalization.v1"

# The handoff-level key under which emitted-section provenance is recorded.
SOURCE_PROVENANCE_FIELD = "section_key_provenance"


class CanonicalSectionCollisionError(ValueError):
    """Two source keys claim one canonical identity. The handoff is refused."""


def normalize_section_key(value: str) -> tuple[str, bool]:
    """Return ``(emitted_key, was_normalized)`` for one source key.

    A key that already is canonical, or that carries no canonical identity at
    all, is returned unchanged with ``was_normalized`` false. Only an accepted
    legacy alias reports true.
    """
    source = str(value or "").strip()
    canonical = canonical_section_key(source)
    if canonical is None or canonical == source:
        return source, False
    return canonical, True


def assert_no_canonical_collisions(
    section_keys: Iterable[str],
    *,
    report_id: str,
    client_id: str,
    project_id: str,
) -> None:
    """Refuse the handoff if any canonical identity is claimed twice.

    Called before the handoff is validated or written, so a collision can never
    produce a partial handoff, partial metadata, or misleading success
    evidence. The existing atomic writer is never reached, so any previously
    published file stays byte-identical.
    """
    collisions = detect_canonical_section_collisions(list(section_keys))
    if not collisions:
        return
    detail = "; ".join(
        f"{item['canonical_section_key']} is claimed by {' and '.join(item['claiming_keys'])}"
        for item in collisions
    )
    raise CanonicalSectionCollisionError(
        f"handoff generation refused: canonical section identities are claimed more than once "
        f"({detail}) for report {report_id}, client {client_id}, project {project_id}. "
        "The importer will not choose between source sections, merge them, or drop either one. "
        "No handoff file was written and any existing handoff is unchanged."
    )


def section_key_provenance(source_key: str, emitted_key: str) -> dict[str, Any] | None:
    """Provenance for one emitted section, or ``None`` when nothing changed.

    Returning ``None`` for an unchanged key is deliberate. Recording a rename
    event that never happened would be a fabricated provenance claim, so an
    already-canonical section carries no normalization record at all.
    """
    if source_key == emitted_key:
        return None
    return {
        "source_section_key": source_key,
        "emitted_section_key": emitted_key,
        "normalization_contract": NORMALIZATION_CONTRACT,
        "normalized_by": "importer",
    }


def normalize_section_payloads(
    payloads: list[Mapping[str, Any]],
    *,
    report_id: str,
    client_id: str,
    project_id: str,
    key_field: str = "section_key",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize ``key_field`` across a list of section-keyed payloads.

    Returns ``(normalized_payloads, provenance_records)``. Collisions are
    detected on the **source** keys before anything is emitted, so a refusal
    happens before any payload is rewritten.

    Payload objects are copied rather than mutated, so a refusal leaves the
    caller's input untouched.
    """
    source_keys = [str(item.get(key_field) or "").strip() for item in payloads]
    assert_no_canonical_collisions(
        source_keys, report_id=report_id, client_id=client_id, project_id=project_id
    )

    normalized: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for item, source in zip(payloads, source_keys):
        emitted, changed = normalize_section_key(source)
        entry = dict(item)
        entry[key_field] = emitted
        normalized.append(entry)
        if changed:
            record = section_key_provenance(source, emitted)
            if record is not None:
                provenance.append(record)
    return normalized, provenance
