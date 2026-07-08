#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
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
    env: Mapping[str, str] | None = None,
    root: Path = ROOT,
    local_config_dir: Path = LOCAL_CONFIG_DIR,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, object]:
    source = os.environ if env is None else env
    slugs = load_registry_slugs(registry_path)
    profiles = [
        _profile_report(profile, slugs=slugs, env=source, root=root, local_config_dir=local_config_dir)
        for profile in PREFLIGHTS
    ]
    return {
        "mode": "preflight-only",
        "provider_calls": "none",
        "local_config_contents_read": "no",
        "profiles": profiles,
        "summary": _summary(profiles),
    }


def _profile_report(
    profile: ProfilePreflight,
    *,
    slugs: set[str],
    env: Mapping[str, str],
    root: Path,
    local_config_dir: Path,
) -> dict[str, object]:
    local_config_path = local_config_dir / f"{profile.slug}.local.json"
    return {
        "slug": profile.slug,
        "display_name": profile.display_name,
        "dashboard_project": profile.dashboard_project,
        "profile_registry": "present" if profile.slug in slugs else "missing",
        "local_config_path": f"local-profile-configs/{profile.slug}.local.json",
        "local_config_file": "present; contents not read" if local_config_path.exists() else "missing",
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
    return {
        "profiles_checked": len(profiles),
        "missing_registry_profiles": missing_registry,
        "missing_env_names": missing_env,
        "path_values_inside_repo": inside_repo,
    }


def format_report(report: Mapping[str, object]) -> str:
    lines = [
        "Client Report Publisher profile config preflight",
        "Mode: preflight-only; provider calls: none; ignored local config contents read: no",
        "",
    ]
    for profile in report.get("profiles", []):
        if not isinstance(profile, Mapping):
            continue
        lines.extend(
            [
                f"Profile: {profile['slug']} ({profile['display_name']})",
                f"  Dashboard project: {profile['dashboard_project']}",
                f"  Registry: {profile['profile_registry']}",
                f"  Local config: {profile['local_config_path']} - {profile['local_config_file']}",
                f"  Provider readiness: {profile['provider_readiness']}",
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight local profile config readiness without reading secrets or calling providers."
    )
    parser.add_argument("--json", action="store_true", help="Print safe JSON status instead of text.")
    args = parser.parse_args()
    report = run_preflight()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
