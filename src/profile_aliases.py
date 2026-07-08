from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_REGISTRY = ROOT / "config" / "dashboard_lab_profiles.json"
PROFILE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

PROFILE_ALIASES: dict[str, str] = {
    "aluma": "aluma-seo-geo",
    "steadfast": "steadfast-decks-and-fences",
    "wws": "western-wood-structures",
    "spanish-head": "inn-at-spanish-head",
    "pinnacle": "pinnacle-contractors",
    "lucy": "lucy-escobar",
    "avs": "avs",
}


class ProfileAliasError(ValueError):
    pass


def resolve_profile_slug(
    profile: str,
    *,
    registry_path: Path = DEFAULT_PROFILE_REGISTRY,
    aliases: Mapping[str, str] = PROFILE_ALIASES,
) -> str:
    requested = _normalize_profile_slug(profile)
    canonical_slugs = load_profile_slugs(registry_path)
    if requested in canonical_slugs:
        return requested
    canonical = aliases.get(requested)
    if canonical and canonical in canonical_slugs:
        return canonical
    if requested == "pinnaacle":
        raise ProfileAliasError("unknown profile alias: pinnaacle; did you mean pinnacle?")
    return requested


def load_profile_slugs(registry_path: Path = DEFAULT_PROFILE_REGISTRY) -> set[str]:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ProfileAliasError("profile registry must contain profiles array")
    return {
        str(item.get("slug") or "").strip()
        for item in profiles
        if isinstance(item, dict) and str(item.get("slug") or "").strip()
    }


def profile_local_config_candidates(profile: str, canonical_profile: str, config_dir: Path) -> list[Path]:
    requested = _normalize_profile_slug(profile)
    candidates = [config_dir / f"{requested}.local.json"]
    canonical_path = config_dir / f"{canonical_profile}.local.json"
    if canonical_path not in candidates:
        candidates.append(canonical_path)
    return candidates


def _normalize_profile_slug(profile: str) -> str:
    normalized = str(profile or "").strip().lower()
    if not PROFILE_SLUG_RE.match(normalized):
        raise ProfileAliasError("profile slug must contain only lowercase letters, numbers, and hyphens")
    return normalized
