import json

import pytest

from src.profile_aliases import ProfileAliasError, resolve_profile_slug


def test_profile_aliases_resolve_to_canonical_slugs(tmp_path):
    registry = tmp_path / "profiles.json"
    registry.write_text(
        json.dumps(
            {
                "profiles": [
                    {"slug": "aluma-seo-geo"},
                    {"slug": "steadfast-decks-and-fences"},
                    {"slug": "western-wood-structures"},
                    {"slug": "inn-at-spanish-head"},
                    {"slug": "pinnacle-contractors"},
                    {"slug": "lucy-escobar"},
                    {"slug": "avs"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert resolve_profile_slug("aluma", registry_path=registry) == "aluma-seo-geo"
    assert resolve_profile_slug("steadfast", registry_path=registry) == "steadfast-decks-and-fences"
    assert resolve_profile_slug("wws", registry_path=registry) == "western-wood-structures"
    assert resolve_profile_slug("spanish-head", registry_path=registry) == "inn-at-spanish-head"
    assert resolve_profile_slug("pinnacle", registry_path=registry) == "pinnacle-contractors"
    assert resolve_profile_slug("lucy", registry_path=registry) == "lucy-escobar"
    assert resolve_profile_slug("avs", registry_path=registry) == "avs"
    assert resolve_profile_slug("aluma-seo-geo", registry_path=registry) == "aluma-seo-geo"


def test_profile_aliases_report_pinnacle_typo_without_permanent_alias(tmp_path):
    registry = tmp_path / "profiles.json"
    registry.write_text(json.dumps({"profiles": [{"slug": "pinnacle-contractors"}]}), encoding="utf-8")

    with pytest.raises(ProfileAliasError, match="did you mean pinnacle"):
        resolve_profile_slug("pinnaacle", registry_path=registry)


def test_profile_aliases_leave_unmapped_valid_slugs_unchanged(tmp_path):
    registry = tmp_path / "profiles.json"
    registry.write_text(json.dumps({"profiles": [{"slug": "aluma-seo-geo"}]}), encoding="utf-8")

    assert resolve_profile_slug("demo-profile", registry_path=registry) == "demo-profile"
