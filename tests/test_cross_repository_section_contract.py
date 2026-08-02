"""Cross-repository agreement between the importer and the Client Report Publisher portal.

The importer and the portal each hold their own copy of the canonical section
vocabulary. That duplication is deliberate: the portal must stay defensive and
must not trust importer output, so a shared runtime package would be the wrong
fix and is not introduced here.

What *is* required is that the two copies never drift. These tests read the
portal's accepted Rust source directly and assert field-level equivalence.

The portal checkout is not a dependency of this repository. When it is absent,
these tests skip with an explicit reason rather than passing silently, so a
skip can never be mistaken for verified agreement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.client_report_publisher_contracts import (
    AMBIGUOUS_SECTION_IDENTIFIERS,
    CANONICAL_SECTION_SOURCE_MATRIX,
    SAFE_LEGACY_SECTION_ALIASES,
)

ROOT = Path(__file__).resolve().parents[1]
PORTAL_CONTRACT = (
    ROOT.parent / "client-dashboard" / "src" / "reporting_contract.rs"
)


def _portal_source() -> str:
    if not PORTAL_CONTRACT.exists():
        pytest.skip(
            f"portal checkout not present at {PORTAL_CONTRACT}; cross-repository "
            "equivalence was NOT verified in this run"
        )
    return PORTAL_CONTRACT.read_text(encoding="utf-8")


def _portal_aliases(source: str) -> dict[str, str]:
    block = re.search(
        r"SAFE_LEGACY_REPORTING_SECTION_ALIASES[^=]*=\s*\[(.*?)\];",
        source,
        re.DOTALL,
    )
    assert block, "portal alias array not found"
    pairs = re.findall(r'\(\s*"([a-z0-9_]+)"\s*,\s*([A-Z0-9_]+)\s*\)', block.group(1))
    resolved: dict[str, str] = {}
    for alias, constant in pairs:
        value = re.search(rf'{constant}\s*:\s*&str\s*=\s*"([a-z0-9_]+)"', source)
        assert value, f"portal constant {constant} not found"
        resolved[alias] = value.group(1)
    return resolved


def test_alias_map_matches_the_portal_exactly() -> None:
    assert _portal_aliases(_portal_source()) == SAFE_LEGACY_SECTION_ALIASES


def test_canonical_section_set_matches_the_portal_exactly() -> None:
    source = _portal_source()
    block = re.search(
        r"CANONICAL_REPORTING_SECTION_KEYS[^=]*=\s*\[(.*?)\];", source, re.DOTALL
    )
    assert block, "portal canonical array not found"
    constants = re.findall(r"([A-Z0-9_]+)\s*,", block.group(1))
    portal_keys = set()
    for constant in constants:
        value = re.search(rf'{constant}\s*:\s*&str\s*=\s*"([a-z0-9_]+)"', source)
        assert value, f"portal constant {constant} not found"
        portal_keys.add(value.group(1))
    assert portal_keys == set(CANONICAL_SECTION_SOURCE_MATRIX)


def test_ambiguous_identifiers_match_the_portal_exactly() -> None:
    source = _portal_source()
    block = re.search(
        r"AMBIGUOUS_REPORTING_SECTION_KEYS[^=]*=\s*\[(.*?)\];", source, re.DOTALL
    )
    assert block, "portal ambiguous array not found"
    portal_keys = set(re.findall(r'"([a-z0-9_]+)"', block.group(1)))
    assert portal_keys == AMBIGUOUS_SECTION_IDENTIFIERS


def test_portal_still_normalizes_defensively_at_its_own_boundary() -> None:
    """The portal must not start trusting importer output.

    Canonical importer output makes the portal's normalization a no-op, not
    unnecessary. If this module ever disappears from the portal, the importer
    would silently become the only line of defense.
    """
    module = ROOT.parent / "client-dashboard" / "src" / "import_normalization.rs"
    if not module.exists():
        pytest.skip("portal checkout not present; defensive normalization NOT verified")
    text = module.read_text(encoding="utf-8")
    assert "plan_section_key_normalization" in text
    assert "detect_canonical_section_collisions" in text
    assert "import_provenance" in text


def test_the_two_provenance_fields_are_distinct_and_truthful() -> None:
    """Importer and portal provenance must not be confusable.

    The portal records ``import_provenance`` when *it* normalizes at import.
    The importer records ``section_key_provenance`` when *it* normalizes at
    generation. Distinct names keep each record truthful about which stage
    performed the rename.
    """
    from src.client_report_section_normalization import SOURCE_PROVENANCE_FIELD

    assert SOURCE_PROVENANCE_FIELD == "section_key_provenance"
    assert SOURCE_PROVENANCE_FIELD != "import_provenance"
