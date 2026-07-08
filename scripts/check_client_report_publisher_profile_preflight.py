#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.profile_aliases import PROFILE_ALIASES, ProfileAliasError, resolve_profile_slug
from src.profile_local_config import load_profile_local_config

REGISTRY_PATH = ROOT / "config" / "dashboard_lab_profiles.json"
LOCAL_CONFIG_DIR = ROOT / "local-profile-configs"


@dataclass(frozen=True)
class EnvCheck:
    name: str
    label: str
    kind: str = "value"


@dataclass(frozen=True)
class ProfilePreflight:
    slug: str
    display_name: str
    dashboard_project: str
    env_checks: tuple[EnvCheck, ...]
    avs_pending: bool = False


PREFLIGHTS: tuple[ProfilePreflight, ...] = (
    ProfilePreflight(
        slug="aluma-seo-geo",
        display_name="Aluma Aesthetic Medicine",
        dashboard_project="Aluma Website Reporting",
        env_checks=(
            EnvCheck("ALUMA_GA4_PROPERTY_ID", "GA4 property id"),
            EnvCheck("ALUMA_GA4_OAUTH_TOKEN_FILE", "GA4 OAuth token file", "path"),
            EnvCheck("ALUMA_GA4_OAUTH_CLIENT_SECRETS", "GA4 OAuth client secrets", "path"),
            EnvCheck("ALUMA_GSC_OAUTH_TOKEN_FILE", "GSC OAuth token file", "path"),
            EnvCheck("ALUMA_GSC_OAUTH_CLIENT_SECRETS", "GSC OAuth client secrets", "path"),
        ),
    ),
    ProfilePreflight(
        slug="inn-at-spanish-head",
        display_name="Inn At Spanish Head",
        dashboard_project="Inn At Spanish Head Website Reporting",
        env_checks=(
            EnvCheck("INN_GA4_PROPERTY_ID", "GA4 property id"),
            EnvCheck("INN_GA4_OAUTH_TOKEN_FILE", "GA4 OAuth token file", "path"),
            EnvCheck("INN_GA4_OAUTH_CLIENT_SECRETS", "GA4 OAuth client secrets", "path"),
            EnvCheck("INN_GSC_OAUTH_TOKEN_FILE", "GSC OAuth token file", "path"),
            EnvCheck("INN_GSC_OAUTH_CLIENT_SECRETS", "GSC OAuth client secrets", "path"),
        ),
    ),
    ProfilePreflight(
        slug="lucy-escobar",
        display_name="Lucy Escobar",
        dashboard_project="Lucy Escobar Website Reporting",
        env_checks=(
            EnvCheck("LUCY_GA4_PROPERTY_ID", "GA4 property id"),
            EnvCheck("LUCY_GA4_OAUTH_TOKEN_FILE", "GA4 OAuth token file", "path"),
            EnvCheck("LUCY_GA4_OAUTH_CLIENT_SECRETS", "GA4 OAuth client secrets", "path"),
            EnvCheck("LUCY_GSC_OAUTH_TOKEN_FILE", "GSC OAuth token file", "path"),
            EnvCheck("LUCY_GSC_OAUTH_CLIENT_SECRETS", "GSC OAuth client secrets", "path"),
        ),
    ),
    ProfilePreflight(
        slug="pinnacle-contractors",
        display_name="Pinnacle Contractors",
        dashboard_project="Pinnacle Contractors Website Reporting",
        env_checks=(
            EnvCheck("PINNACLE_GA4_PROPERTY_ID", "GA4 property id"),
            EnvCheck("PINNACLE_GA4_OAUTH_TOKEN_FILE", "GA4 OAuth token file", "path"),
            EnvCheck("PINNACLE_GA4_OAUTH_CLIENT_SECRETS", "GA4 OAuth client secrets", "path"),
            EnvCheck("PINNACLE_GSC_OAUTH_TOKEN_FILE", "GSC OAuth token file", "path"),
            EnvCheck("PINNACLE_GSC_OAUTH_CLIENT_SECRETS", "GSC OAuth client secrets", "path"),
        ),
    ),
    ProfilePreflight(
        slug="western-wood-structures",
        display_name="Western Wood Structures",
        dashboard_project="Western Wood Structures Website Reporting",
        env_checks=(
            EnvCheck("WWS_GA4_PROPERTY_ID", "GA4 property id"),
            EnvCheck("WWS_GA4_OAUTH_TOKEN_FILE", "GA4 OAuth token file", "path"),
            EnvCheck("WWS_GA4_OAUTH_CLIENT_SECRETS", "GA4 OAuth client secrets", "path"),
            EnvCheck("WWS_GSC_OAUTH_TOKEN_FILE", "GSC OAuth token file", "path"),
            EnvCheck("WWS_GSC_OAUTH_CLIENT_SECRETS", "GSC OAuth client secrets", "path"),
        ),
    ),
    ProfilePreflight(
        slug="steadfast-decks-and-fences",
        display_name="Steadfast Decks and Fences",
        dashboard_project="Steadfast Decks and Fences Website Reporting",
        env_checks=(
            EnvCheck("STEADFAST_GA4_PROPERTY_ID", "GA4 property id"),
            EnvCheck("STEADFAST_GA4_OAUTH_TOKEN_FILE", "GA4 OAuth token file", "path"),
            EnvCheck("STEADFAST_GA4_OAUTH_CLIENT_SECRETS", "GA4 OAuth client secrets", "path"),
            EnvCheck("STEADFAST_GSC_OAUTH_TOKEN_FILE", "GSC OAuth token file", "path"),
            EnvCheck("STEADFAST_GSC_OAUTH_CLIENT_SECRETS", "GSC OAuth client secrets", "path"),
        ),
    ),
    ProfilePreflight(
        slug="avs",
        display_name="AVS",
        dashboard_project="AVS Website Reporting",
        env_checks=(
            EnvCheck("AVS_CANONICAL_DOMAIN_PENDING", "canonical domain confirmation"),
            EnvCheck("AVS_GA4_PROPERTY_ID_PENDING", "pending GA4 property id"),
            EnvCheck("AVS_GSC_SITE_URL_PENDING", "pending GSC site URL"),
        ),
        avs_pending=True,
    ),
)


def load_registry_slugs(path: Path = REGISTRY_PATH) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("profile registry must contain profiles array")
    return {
        str(item.get("slug") or "").strip()
        for item in profiles
        if isinstance(item, dict) and str(item.get("slug") or "").strip()
    }


def run_preflight(
    *,
    profiles: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    root: Path = ROOT,
    local_config_dir: Path = LOCAL_CONFIG_DIR,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, object]:
    source = os.environ if env is None else env
    slugs = load_registry_slugs(registry_path)
    selected = _selected_preflights(profiles)
    profile_reports = [
        _profile_report(
            profile,
            input_profile=input_profile,
            slugs=slugs,
            env=source,
            root=root,
            local_config_dir=local_config_dir,
            registry_path=registry_path,
        )
        for input_profile, profile in selected
    ]
    return {
        "mode": "preflight-only",
        "provider_calls": "none",
        "local_config_contents_read": "requested profile only; values redacted",
        "profiles": profile_reports,
        "summary": _summary(profile_reports),
    }


def _profile_report(
    profile: ProfilePreflight,
    *,
    input_profile: str,
    slugs: set[str],
    env: Mapping[str, str],
    root: Path,
    local_config_dir: Path,
    registry_path: Path,
) -> dict[str, object]:
    try:
        canonical = resolve_profile_slug(input_profile, registry_path=registry_path)
        alias_error = ""
    except ProfileAliasError as exc:
        canonical = profile.slug
        alias_error = str(exc)
    local_config = load_profile_local_config(input_profile, config_dir=local_config_dir, env=env)
    local_config_path = local_config.path
    ga4 = local_config.provider("ga4")
    gsc = local_config.provider("gsc")
    return {
        "input_profile": input_profile,
        "slug": profile.slug,
        "canonical_profile": canonical,
        "display_name": profile.display_name,
        "dashboard_project": profile.dashboard_project,
        "alias_resolution": "ok" if not alias_error else "error",
        "alias_error": alias_error,
        "profile_registry": "present" if profile.slug in slugs else "missing",
        "local_config_path": _safe_config_path_label(local_config_path, local_config_dir),
        "local_config_file": "present; values redacted" if local_config_path.exists() else "missing",
        "local_config_valid": "yes" if local_config.valid else "no",
        "ga4": _ga4_report(ga4),
        "gsc": _gsc_report(gsc),
        "env": [_env_report(check, env=env, root=root) for check in profile.env_checks],
        "provider_readiness": "pending canonical domain confirmation" if profile.avs_pending else "ready for local config once env/path checks pass",
    }


def _env_report(check: EnvCheck, *, env: Mapping[str, str], root: Path) -> dict[str, str]:
    value = env.get(check.name)
    report = {
        "name": check.name,
        "label": check.label,
        "status": "set" if value else "missing",
    }
    if check.kind == "path":
        if not value:
            report["file"] = "not checked"
            report["repo_location"] = "not checked"
        else:
            path = Path(value).expanduser()
            report["file"] = "exists" if path.exists() else "missing"
            report["repo_location"] = "inside repo" if _is_inside(path, root) else "outside repo"
    return report


def _ga4_report(ga4: Mapping[str, object]) -> dict[str, str]:
    return {
        "property_id": "configured" if ga4.get("property_id_configured") else "missing",
        "oauth_client_secrets": _path_status(ga4, "oauth_client_secrets"),
        "oauth_token_file": _path_status(ga4, "oauth_token"),
    }


def _gsc_report(gsc: Mapping[str, object]) -> dict[str, str]:
    return {
        "site_url": "configured" if gsc.get("site_url_configured") else "missing",
        "oauth_client_secrets": _path_status(gsc, "oauth_client_secrets"),
        "oauth_token_file": _path_status(gsc, "oauth_token"),
    }


def _path_status(config: Mapping[str, object], prefix: str) -> str:
    configured = bool(
        config.get(f"{prefix}_configured")
        or config.get(f"{prefix}_file_configured")
        or config.get(f"{prefix}_env_present")
    )
    if not configured:
        return "missing"
    exists = "exists" if config.get(f"{prefix}_file_exists") else "missing file"
    location = str(
        config.get(f"{prefix}_repo_location")
        or config.get(f"{prefix}_file_repo_location")
        or "not checked"
    )
    return f"configured; {exists}; {location}"


def _is_inside(path: Path, root: Path) -> bool:
    try:
        resolved_path = path.resolve(strict=False)
        resolved_root = root.resolve(strict=False)
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def _summary(profiles: list[dict[str, object]]) -> dict[str, int]:
    env_rows = [
        row
        for profile in profiles
        for row in profile.get("env", [])
        if isinstance(row, dict)
    ]
    inside_repo = sum(1 for row in env_rows if row.get("repo_location") == "inside repo")
    missing_env = sum(1 for row in env_rows if row.get("status") == "missing")
    missing_registry = sum(1 for profile in profiles if profile.get("profile_registry") == "missing")
    inside_repo_config = sum(
        1
        for profile in profiles
        for provider in ("ga4", "gsc")
        for value in (profile.get(provider) or {}).values()
        if isinstance(value, str) and "inside repo" in value
    )
    return {
        "profiles_checked": len(profiles),
        "missing_registry_profiles": missing_registry,
        "missing_env_names": missing_env,
        "path_values_inside_repo": inside_repo + inside_repo_config,
    }


def format_report(report: Mapping[str, object]) -> str:
    lines = [
        "Client Report Publisher profile config preflight",
        "Mode: preflight-only; provider calls: none; local config values redacted",
        "",
    ]
    for profile in report.get("profiles", []):
        if not isinstance(profile, Mapping):
            continue
        lines.extend(
            [
                f"Profile: {profile['input_profile']} -> {profile['canonical_profile']} ({profile['display_name']})",
                f"  Dashboard project: {profile['dashboard_project']}",
                f"  Registry: {profile['profile_registry']}",
                f"  Local config: {profile['local_config_path']} - {profile['local_config_file']}; valid {profile['local_config_valid']}",
                f"  Provider readiness: {profile['provider_readiness']}",
                f"  GA4: property {profile['ga4']['property_id']}; client secrets {profile['ga4']['oauth_client_secrets']}; token {profile['ga4']['oauth_token_file']}",
                f"  GSC: site URL {profile['gsc']['site_url']}; client secrets {profile['gsc']['oauth_client_secrets']}; token {profile['gsc']['oauth_token_file']}",
            ]
        )
        for row in profile.get("env", []):
            if not isinstance(row, Mapping):
                continue
            suffix = ""
            if "file" in row:
                suffix = f"; file {row['file']}; {row['repo_location']}"
            lines.append(f"    {row['name']}: {row['status']}{suffix}")
        lines.append("")
    summary = report.get("summary", {})
    if isinstance(summary, Mapping):
        lines.extend(
            [
                "Summary:",
                f"  Profiles checked: {summary.get('profiles_checked')}",
                f"  Missing registry profiles: {summary.get('missing_registry_profiles')}",
                f"  Missing env names: {summary.get('missing_env_names')}",
                f"  Path values inside repo: {summary.get('path_values_inside_repo')}",
            ]
        )
    return "\n".join(lines)


def _selected_preflights(profile_inputs: list[str] | None) -> list[tuple[str, ProfilePreflight]]:
    by_slug = {profile.slug: profile for profile in PREFLIGHTS}
    selected_inputs = profile_inputs or [profile.slug for profile in PREFLIGHTS]
    selected: list[tuple[str, ProfilePreflight]] = []
    for input_profile in selected_inputs:
        try:
            canonical = resolve_profile_slug(input_profile)
        except ProfileAliasError:
            canonical = str(input_profile or "").strip().lower()
        selected.append((input_profile, by_slug.get(canonical, ProfilePreflight(canonical, canonical, "", ()))))
    return selected


def _safe_config_path_label(path: Path, config_dir: Path) -> str:
    try:
        return f"local-profile-configs/{path.resolve(strict=False).relative_to(config_dir.resolve(strict=False)).as_posix()}"
    except ValueError:
        return path.name


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight local profile config readiness without reading secrets or calling providers."
    )
    parser.add_argument(
        "--profile",
        action="append",
        help="Profile slug or alias to check. Repeat for multiple profiles. Defaults to the next-client batch.",
    )
    parser.add_argument(
        "--local-config-dir",
        default=str(LOCAL_CONFIG_DIR),
        help="Directory containing ignored local profile configs. Defaults to local-profile-configs.",
    )
    parser.add_argument("--json", action="store_true", help="Print safe JSON status instead of text.")
    args = parser.parse_args()
    report = run_preflight(profiles=args.profile, local_config_dir=Path(args.local_config_dir))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
