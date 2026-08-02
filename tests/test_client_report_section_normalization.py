"""Importer canonical section-key output, provenance, and collision refusal.

Every test runs fully offline against synthetic fixtures. No real client
artifact is read, copied, edited, or relabeled, and no comparison contract is
synthesized beyond the minimal section-keyed payloads these tests need.
"""

from __future__ import annotations

import pytest

from src.client_report_publisher_contracts import (
    canonical_section_key,
    detect_canonical_section_collisions,
)
from src.client_report_section_normalization import (
    NORMALIZATION_CONTRACT,
    CanonicalSectionCollisionError,
    normalize_section_key,
    normalize_section_payloads,
    section_key_provenance,
)

IDENTITY = {
    "report_id": "00000000-0000-4000-8000-00000000r8ID".replace("r8ID", "0001"),
    "client_id": "00000000-0000-4000-8000-000000000002",
    "project_id": "00000000-0000-4000-8000-000000000003",
}


def _sections(*keys: str) -> list[dict[str, object]]:
    return [{"section_key": key, "preset_key": "report_period"} for key in keys]


# Resolver agreement with the portal


def test_canonical_keys_resolve_to_themselves() -> None:
    for key in ["ga4_top_metrics", "ga4_website_traffic_trends", "gsc_top_pages"]:
        assert canonical_section_key(key) == key


def test_each_accepted_legacy_alias_maps_to_the_expected_canonical_key() -> None:
    assert canonical_section_key("ga4_traffic_trends") == "ga4_website_traffic_trends"
    assert canonical_section_key("ga4_traffic_channels") == "ga4_channel_performance"
    assert canonical_section_key("ga4_top_pages") == "ga4_most_viewed_pages"


def test_ambiguous_and_unknown_keys_carry_no_canonical_identity() -> None:
    for key in ["traffic_trends", "top_pages", "ga4_explorer_source", "not_a_section", ""]:
        assert canonical_section_key(key) is None


# Emitted keys


def test_canonical_input_key_remains_canonical_and_reports_no_rename() -> None:
    emitted, changed = normalize_section_key("ga4_website_traffic_trends")
    assert emitted == "ga4_website_traffic_trends"
    assert changed is False


def test_each_alias_emits_the_canonical_key_and_reports_a_rename() -> None:
    for alias, canonical in [
        ("ga4_traffic_trends", "ga4_website_traffic_trends"),
        ("ga4_traffic_channels", "ga4_channel_performance"),
        ("ga4_top_pages", "ga4_most_viewed_pages"),
    ]:
        emitted, changed = normalize_section_key(alias)
        assert emitted == canonical
        assert changed is True


def test_unknown_key_is_emitted_unchanged() -> None:
    # Normalization changes spelling, never what counts as a canonical section.
    emitted, changed = normalize_section_key("ga4_explorer_source")
    assert emitted == "ga4_explorer_source"
    assert changed is False


def test_handoff_payload_emits_canonical_keys() -> None:
    normalized, _ = normalize_section_payloads(
        _sections("ga4_traffic_trends", "ga4_traffic_channels", "ga4_top_metrics"), **IDENTITY
    )
    assert [item["section_key"] for item in normalized] == [
        "ga4_website_traffic_trends",
        "ga4_channel_performance",
        "ga4_top_metrics",
    ]


# Provenance


def test_original_source_key_provenance_is_preserved() -> None:
    _, provenance = normalize_section_payloads(_sections("ga4_traffic_trends"), **IDENTITY)
    assert len(provenance) == 1
    assert provenance[0]["source_section_key"] == "ga4_traffic_trends"
    assert provenance[0]["emitted_section_key"] == "ga4_website_traffic_trends"
    assert provenance[0]["normalization_contract"] == NORMALIZATION_CONTRACT
    assert provenance[0]["normalized_by"] == "importer"


def test_no_rename_event_is_invented_for_an_already_canonical_key() -> None:
    assert section_key_provenance("gsc_summary", "gsc_summary") is None
    _, provenance = normalize_section_payloads(_sections("ga4_top_metrics", "gsc_summary"), **IDENTITY)
    assert provenance == []


def test_provenance_does_not_claim_a_portal_import_occurred() -> None:
    _, provenance = normalize_section_payloads(_sections("ga4_top_pages"), **IDENTITY)
    serialized = repr(provenance).lower()
    assert "import_provenance" not in serialized
    assert provenance[0]["normalized_by"] == "importer"


def test_other_payload_fields_are_preserved() -> None:
    payload = [{"section_key": "ga4_traffic_trends", "preset_key": "last_30_days", "metrics": [1, 2]}]
    normalized, _ = normalize_section_payloads(payload, **IDENTITY)
    assert normalized[0]["preset_key"] == "last_30_days"
    assert normalized[0]["metrics"] == [1, 2]


def test_input_payloads_are_not_mutated() -> None:
    payload = _sections("ga4_traffic_trends")
    normalize_section_payloads(payload, **IDENTITY)
    assert payload[0]["section_key"] == "ga4_traffic_trends"


# Collisions


def test_canonical_plus_alias_collision_is_rejected() -> None:
    with pytest.raises(CanonicalSectionCollisionError) as exc:
        normalize_section_payloads(
            _sections("ga4_website_traffic_trends", "ga4_traffic_trends"), **IDENTITY
        )
    message = str(exc.value)
    assert "ga4_website_traffic_trends" in message
    assert "ga4_traffic_trends" in message
    assert "No handoff file was written" in message


def test_two_keys_resolving_to_one_canonical_identity_are_rejected() -> None:
    with pytest.raises(CanonicalSectionCollisionError):
        normalize_section_payloads(
            _sections("ga4_traffic_channels", "ga4_traffic_channels"), **IDENTITY
        )


def test_collision_message_names_report_client_and_project_identity() -> None:
    with pytest.raises(CanonicalSectionCollisionError) as exc:
        normalize_section_payloads(
            _sections("ga4_top_pages", "ga4_most_viewed_pages"), **IDENTITY
        )
    message = str(exc.value)
    assert IDENTITY["report_id"] in message
    assert IDENTITY["client_id"] in message
    assert IDENTITY["project_id"] in message


def test_collision_refuses_rather_than_deduplicating_or_merging() -> None:
    with pytest.raises(CanonicalSectionCollisionError) as exc:
        normalize_section_payloads(
            _sections("ga4_traffic_trends", "ga4_website_traffic_trends"), **IDENTITY
        )
    assert "will not choose between source sections, merge them, or drop either one" in str(exc.value)


def test_helper_sections_never_collide() -> None:
    normalized, provenance = normalize_section_payloads(
        _sections("ga4_explorer_source", "ga4_explorer_landing_pages", "ga4_top_sources"), **IDENTITY
    )
    assert len(normalized) == 3
    assert provenance == []


def test_a_valid_alias_only_section_set_is_not_a_collision() -> None:
    normalized, provenance = normalize_section_payloads(
        _sections("ga4_traffic_trends", "ga4_traffic_channels", "ga4_top_metrics"), **IDENTITY
    )
    assert len(normalized) == 3
    assert len(provenance) == 2


def test_collision_detector_is_deterministic() -> None:
    keys = ["ga4_traffic_trends", "ga4_website_traffic_trends"]
    assert detect_canonical_section_collisions(keys) == detect_canonical_section_collisions(
        list(reversed(keys))
    )


# Failed collision writes nothing


def test_failed_collision_writes_no_handoff_and_preserves_existing_output(tmp_path) -> None:
    """A refused generation must leave any existing published file untouched.

    Normalization raises before the writer is ever reached, so the atomic
    publication path from the accepted remote correction is never entered.
    """
    existing = tmp_path / "client_report_presentation_comparisons.v1.json"
    original_bytes = b'{"existing": "valid handoff"}\n'
    existing.write_bytes(original_bytes)

    with pytest.raises(CanonicalSectionCollisionError):
        normalize_section_payloads(
            _sections("ga4_traffic_trends", "ga4_website_traffic_trends"), **IDENTITY
        )

    assert existing.read_bytes() == original_bytes
    assert list(tmp_path.iterdir()) == [existing]
    assert not any(path.name.startswith(".") for path in tmp_path.iterdir())
