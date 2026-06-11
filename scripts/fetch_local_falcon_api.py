from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_falcon_api_plan import (
    LocalFalconApiPlanError,
    build_direct_plan,
    build_manifest_plan,
    default_output_path,
    mask_report_id,
    redact_query_text,
    render_plan,
    summarize_query_type_counts,
    summarize_source_counts,
)
from src.local_falcon_api_fetcher import LocalFalconApiFetchRequest
from src.local_falcon_api_fetcher import LocalFalconApiFetcher, LocalFalconApiFetcherError
from src.local_falcon_api_live_transport import LocalFalconLiveTransportError, LocalFalconReadOnlyLiveTransport
from src.local_falcon_api_writer import (
    SyntheticFixtureLocalFalconTransport,
    fetch_validate_and_write_summary,
    is_safe_local_falcon_api_write_path,
)
from src.local_falcon_importer import validate_local_falcon_summary
from src.profile_local_config import load_profile_local_config


DEFAULT_LIVE_MANIFEST_REPORT_CAP = 4
ABSOLUTE_LIVE_MANIFEST_REPORT_CAP = 25


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan a future read-only Local Falcon API fetch without making network calls."
    )
    parser.add_argument("--profile", help="Dashboard-lab profile slug.")
    parser.add_argument("--report-id", help="Existing Local Falcon report id/key. Value is treated as local-only.")
    parser.add_argument("--keyword", help="Keyword label for direct report planning.")
    parser.add_argument("--manifest", help="Ignored local manifest with future report retrieval plan.")
    parser.add_argument("--output", help="Output JSON path. Defaults to exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json.")
    parser.add_argument("--out", dest="raw_output_dir", help="Ignored local raw output directory for live read-only report payloads.")
    parser.add_argument("--raw-output-dir", dest="raw_output_dir", help="Ignored local raw output directory for live read-only report payloads.")
    parser.add_argument("--api-key-env", help="Profile-specific Local Falcon API key environment variable name.")
    parser.add_argument(
        "--allow-global-api-key",
        action="store_true",
        help="Allow fallback to LOCAL_FALCON_API_KEY when no profile-specific key is selected.",
    )
    parser.add_argument("--featured-keyword-id", help="Optional featured keyword id for future merge behavior.")
    parser.add_argument("--dry-run", action="store_true", help="Accepted for clarity; no live API calls are made.")
    parser.add_argument("--verbose-plan", action="store_true", help="Show redacted per-report plan rows.")
    parser.add_argument("--no-write", action="store_true", help="Accepted for clarity; suppresses fake output writes unless --write is present.")
    parser.add_argument("--transport", choices=["fake", "live"], help="Transport mode. Live requires --execute and LOCAL_FALCON_API_KEY.")
    parser.add_argument("--write", action="store_true", help="Write fake-transport output to a safe ignored/test path.")
    parser.add_argument("--validate-only", action="store_true", help="Validate an existing local summary file only.")
    parser.add_argument("--replace", action="store_true", help="Plan replacement of matching keyword scans.")
    parser.add_argument("--append", action="store_true", help="Plan appending new keyword scans.")
    parser.add_argument("--timeout", type=int, help="Future request timeout in seconds.")
    parser.add_argument("--max-retries", type=int, help="Future bounded retry count.")
    parser.add_argument(
        "--max-reports",
        type=int,
        help=(
            "Explicit live manifest report allowance. Defaults to 4. "
            f"Cannot exceed {ABSOLUTE_LIVE_MANIFEST_REPORT_CAP}."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Not supported. Live Local Falcon API execution is not implemented.",
    )
    args = parser.parse_args()

    try:
        _apply_profile_defaults(args)
        api_key_env = _resolve_local_falcon_api_key_env(
            args.profile,
            args.api_key_env,
            args.allow_global_api_key,
            manifest_path=args.manifest,
        )
        if args.execute and args.transport != "live":
            raise LocalFalconApiPlanError(
                "Live Local Falcon API execution requires --transport live."
            )
        if args.validate_only:
            return _validate_only(args)
        if args.manifest:
            plan = build_manifest_plan(
                Path(args.manifest),
                profile_override=args.profile,
                output_override=args.output,
                featured_keyword_id_override=args.featured_keyword_id,
                replace=args.replace,
                append=args.append,
                dry_run=not args.write,
                no_write=True if args.no_write or not args.write else False,
                timeout=args.timeout,
                max_retries=args.max_retries,
                api_key_env=api_key_env,
                allow_global_api_key=args.allow_global_api_key,
            )
        else:
            plan = build_direct_plan(
                profile=args.profile,
                keyword=args.keyword,
                report_id=args.report_id,
                output=args.output,
                featured_keyword_id=args.featured_keyword_id,
                replace=args.replace,
                append=args.append,
                dry_run=not args.write,
                no_write=True if args.no_write or not args.write else False,
                timeout=args.timeout,
                max_retries=args.max_retries,
                api_key_env=api_key_env,
                allow_global_api_key=args.allow_global_api_key,
            )
    except (LocalFalconApiPlanError, OSError) as exc:
        print(f"Local Falcon API dry run failed safely: {exc}", file=sys.stderr)
        return 1

    if args.transport == "live":
        try:
            return _run_live_mode(args, plan)
        except (LocalFalconApiPlanError, LocalFalconLiveTransportError, LocalFalconApiFetcherError, OSError) as exc:
            print(f"Local Falcon API live read-only failed safely: {exc}", file=sys.stderr)
            return 1

    if args.write:
        try:
            _write_fake_output(args, plan)
        except (LocalFalconApiPlanError, OSError) as exc:
            print(f"Local Falcon API fake write failed safely: {exc}", file=sys.stderr)
            return 1
        return 0

    print(render_plan(plan, verbose=args.verbose_plan))
    if args.transport == "fake":
        print("")
        print("Fake transport selected, but --write was not provided. No output was written.")
    return 0


def _validate_only(args: argparse.Namespace) -> int:
    profile = args.profile
    if not profile:
        raise LocalFalconApiPlanError("--profile is required for --validate-only")
    path = Path(args.output) if args.output else default_output_path(profile)
    if not path.exists():
        raise LocalFalconApiPlanError(
            f"validation cannot run because no local summary file exists at {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalFalconApiPlanError("local summary file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LocalFalconApiPlanError("local summary file must contain a JSON object")
    result = validate_local_falcon_summary(payload, path)
    print("Validated existing Local Falcon summary output")
    print(f"Profile: {result.profile}")
    print(f"Output: {path}")
    print(f"Keyword scans: {result.keyword_scan_count}")
    print("No network requests were made.")
    return 0


def _write_fake_output(args: argparse.Namespace, plan) -> None:
    if args.transport != "fake":
        raise LocalFalconApiPlanError("--write is only available with --transport fake")
    if args.execute:
        raise LocalFalconApiPlanError("live execution is still disabled; use --transport fake without --execute")
    if args.no_write:
        raise LocalFalconApiPlanError("--write and --no-write cannot be used together")
    if not is_safe_local_falcon_api_write_path(plan.output, cwd=ROOT):
        raise LocalFalconApiPlanError(
            "--write only allows ignored exports/local-real/ paths or .test-tmp-* test paths"
        )
    request = LocalFalconApiFetchRequest(
        profile=plan.profile,
        reports=plan.reports,
        output=plan.output,
        featured_keyword_id=plan.featured_keyword_id,
        dry_run=False,
        no_write=False,
    )
    result = fetch_validate_and_write_summary(request, SyntheticFixtureLocalFalconTransport())
    print("Wrote synthetic Local Falcon API summary")
    print(f"Profile: {plan.profile}")
    print(f"Output: {result.output_path}")
    print(f"Keyword scans: {result.keyword_count}")
    print(f"Created: {'yes' if result.created else 'no'}")
    print(f"Updated: {'yes' if result.updated else 'no'}")
    print(f"Source type: {result.source_type}")
    print("No network requests were made.")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")


def _run_live_mode(args: argparse.Namespace, plan) -> int:
    if args.manifest:
        _validate_live_manifest_report_count(plan, args.max_reports)
    if not args.manifest and len(plan.reports) != 1:
        raise LocalFalconApiPlanError("direct live read-only mode is limited to one report")
    if args.manifest and args.execute and not args.write and not args.raw_output_dir:
        raise LocalFalconApiPlanError("live manifest execution requires --write or --out for ignored raw output")
    if args.write and args.no_write:
        raise LocalFalconApiPlanError("--write and --no-write cannot be used together")
    if args.write and not is_safe_local_falcon_api_write_path(plan.output, cwd=ROOT):
        raise LocalFalconApiPlanError(
            "live writes only allow ignored exports/local-real/ paths or .test-tmp-* test paths"
        )
    raw_output_dir = Path(args.raw_output_dir) if args.raw_output_dir else None
    if raw_output_dir and not _is_safe_local_falcon_raw_output_dir(raw_output_dir):
        raise LocalFalconApiPlanError("raw output directory must be under ignored local/ or .test-tmp-*")
    _print_live_preflight(
        plan,
        will_execute=args.execute,
        will_write=args.write,
        raw_output_dir=raw_output_dir,
        verbose=args.verbose_plan,
    )
    if not args.execute:
        print("")
        print("Dry run only. No Local Falcon network request was made.")
        return 0

    transport = LocalFalconReadOnlyLiveTransport.from_env(
        api_key_env=plan.api_key_env,
        allow_global_fallback=False,
    )
    if raw_output_dir:
        _fetch_and_write_raw_report_payloads(plan, transport, raw_output_dir)
        if not args.write:
            return 0

    request = LocalFalconApiFetchRequest(
        profile=plan.profile,
        reports=plan.reports,
        output=plan.output,
        featured_keyword_id=plan.featured_keyword_id,
        source_type="api_local_real",
        real_data=True,
        dry_run=False,
        no_write=not args.write,
    )
    if args.write:
        result = fetch_validate_and_write_summary(request, transport, preserve_existing=not args.manifest)
        payload = json.loads(result.output_path.read_text(encoding="utf-8"))
        _print_live_output_summary(payload, result.output_path, result.warnings)
    else:
        result = LocalFalconApiFetcher(transport).fetch(request)
        _print_live_output_summary(result.summary, result.output_path, result.warnings, wrote=False)
    return 0


def _validate_live_manifest_report_count(plan, max_reports: int | None) -> None:
    allowed_reports = max_reports or DEFAULT_LIVE_MANIFEST_REPORT_CAP
    if allowed_reports > ABSOLUTE_LIVE_MANIFEST_REPORT_CAP:
        raise LocalFalconApiPlanError(
            f"--max-reports cannot exceed {ABSOLUTE_LIVE_MANIFEST_REPORT_CAP}"
        )
    if allowed_reports < 1:
        raise LocalFalconApiPlanError("--max-reports must be at least 1")
    if len(plan.reports) > allowed_reports:
        raise LocalFalconApiPlanError(
            f"live manifest mode selected {len(plan.reports)} reports; "
            f"pass --max-reports {len(plan.reports)} or less restrictive approved value "
            f"to exceed the default cap of {DEFAULT_LIVE_MANIFEST_REPORT_CAP}"
        )


def _print_live_preflight(
    plan,
    *,
    will_execute: bool,
    will_write: bool,
    raw_output_dir: Path | None = None,
    verbose: bool = False,
) -> None:
    source_counts = summarize_source_counts(plan.reports)
    query_type_counts = summarize_query_type_counts(plan.reports)
    lines = [
        "Local Falcon live read-only preflight",
        f"Profile: {plan.profile}",
        f"Output: {plan.output}",
        f"Raw output directory: {raw_output_dir or '[not requested]'}",
        "Transport: live",
        "Mode: read-only report retrieval",
        "On-Demand scans: disabled",
        "Provider mutation: disabled",
        f"API key env: {plan.api_key_env or '[not selected]'}",
        f"API key configured: {'yes' if plan.api_key_configured else 'no'}",
        f"Write output: {'yes' if will_write else 'no'}",
        "Validator: local_falcon_summary.v2 before write",
        f"Timeout: {plan.timeout_seconds} seconds",
        f"Max retries: {plan.max_retries}",
        f"Execute network request: {'yes' if will_execute else 'no'}",
        f"Reports planned: {len(plan.reports)}",
    ]
    lines.append("Reports by source:")
    for source, count in sorted(source_counts.items()):
        lines.append(f"- {source}: {count}")
    lines.append("Reports by query type:")
    for query_type, count in sorted(query_type_counts.items()):
        lines.append(f"- {query_type}: {count}")
    lines.append("Report IDs, prompts, and raw payloads are not printed.")
    if verbose:
        lines.append("Verbose report plan:")
        for index, report in enumerate(plan.reports, start=1):
            lines.append(f"{index}. Source: {report.source_label or report.source_id or 'Local Falcon'}")
            lines.append(f"   Query type: {report.query_type or 'map_keyword'}")
            lines.append(f"   Query: {redact_query_text(report.query or report.keyword)}")
            lines.append(f"   Report ID: {mask_report_id(report.report_id)}")
    print("\n".join(lines))


def _fetch_and_write_raw_report_payloads(plan, transport, raw_output_dir: Path) -> None:
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    fetched_count = 0
    failed_count = 0
    source_counts = summarize_source_counts(plan.reports)
    fetcher = LocalFalconApiFetcher(transport)

    for index, report in enumerate(plan.reports, start=1):
        try:
            bundle = fetcher.fetch_report_bundle(report)
            payload = {
                "profile": plan.profile,
                "source_id": report.source_id,
                "source_label": report.source_label,
                "query_type": report.query_type,
                "scan_kind": report.scan_kind,
                "report_id_redacted": _redacted_report_id(report.report_id),
                "responses": {
                    "report_summary": bundle.report_summary,
                    "grid_points": bundle.grid_points,
                    "competitors": bundle.competitors,
                    "ai_analysis": bundle.ai_analysis,
                },
            }
            _write_json(raw_output_dir / f"report-{index:03d}.json", payload)
            fetched_count += 1
        except LocalFalconApiFetcherError:
            failed_count += 1

    print("")
    print("Local Falcon raw read-only fetch result")
    print(f"Total reports selected: {len(plan.reports)}")
    print("Reports by source:")
    for source, count in sorted(source_counts.items()):
        print(f"- {source}: {count}")
    print(f"Fetched count: {fetched_count}")
    print("Skipped count: 0")
    print(f"Failed count: {failed_count}")
    print(f"Output directory: {raw_output_dir}")
    print("Report IDs, prompts, API keys, and raw payloads were not printed.")
    if failed_count:
        raise LocalFalconApiFetcherError("one or more Local Falcon reports failed during raw read-only fetch")


def _print_live_output_summary(payload: dict, output_path: Path, warnings: list[str], *, wrote: bool = True) -> None:
    scans = [item for item in payload.get("keyword_scans", []) if isinstance(item, dict)]
    print("")
    print("Local Falcon live read-only result")
    print(f"Output written: {'yes' if wrote else 'no'}")
    print(f"Output: {output_path}")
    print(f"Schema version: {payload.get('schema_version')}")
    print(f"Source type: {payload.get('source_type')}")
    print(f"Real data: {payload.get('real_data')}")
    print(f"Scans: {len(scans)}")
    for scan in scans:
        counts = scan.get("data_points") if isinstance(scan.get("data_points"), dict) else {}
        grid = scan.get("rendered_grid") if isinstance(scan.get("rendered_grid"), dict) else {}
        competitors = scan.get("competitors") if isinstance(scan.get("competitors"), list) else []
        ai = scan.get("ai_analysis") if isinstance(scan.get("ai_analysis"), dict) else {}
        print(f"- Source: {scan.get('source_label') or 'Local Falcon'}")
        print(f"  Query type: {scan.get('query_type') or 'map_keyword'}")
        print(f"  Query: {redact_query_text(str(scan.get('query') or scan.get('keyword') or ''))}")
        print(f"  Report ID: {scan.get('report_id_redacted') or '[not recorded]'}")
        print(f"  Data points: total={counts.get('total')} found={counts.get('found')} top_3={counts.get('top_3')} top_10={counts.get('top_10')}")
        print(f"  Rendered grid: {grid.get('rows')} x {grid.get('columns')}")
        print(f"  Competitors: {len(competitors)}")
        print(f"  AI analysis available: {'yes' if ai.get('available') else 'no'}")
    print("Validation: completed")
    print("Scan creation or provider mutation: none")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")


def _redacted_report_id(value: str) -> str:
    text = str(value)
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"


def _is_safe_local_falcon_raw_output_dir(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        relative = path.as_posix()
    return (
        relative.startswith("local/")
        or relative.startswith(".test-tmp-")
        or "/.test-tmp-" in relative
    )


def _write_json(path: Path, payload: dict) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _apply_profile_defaults(args: argparse.Namespace) -> None:
    if not args.profile:
        return
    config = load_profile_local_config(args.profile).provider("local_falcon")
    if not args.manifest and config.get("manifest_path"):
        args.manifest = str(config["manifest_path"])


def _resolve_local_falcon_api_key_env(
    profile: str | None,
    explicit_env: str | None,
    allow_global: bool,
    *,
    manifest_path: str | None = None,
) -> str | None:
    if explicit_env and explicit_env.strip():
        return explicit_env.strip()

    if not profile and manifest_path:
        profile = _profile_from_manifest(Path(manifest_path))

    if profile:
        profile_env = _profile_specific_api_key_env(profile)
        if os.environ.get(profile_env):
            return profile_env

        local_config_env = _local_falcon_config_api_key_env(profile)
        if local_config_env:
            return local_config_env

        profile_config_env = str(load_profile_local_config(profile).provider("local_falcon").get("api_key_env") or "").strip()
        if _is_env_var_name(profile_config_env) and profile_config_env != "LOCAL_FALCON_API_KEY":
            return profile_config_env

        if profile_env:
            return profile_env

    return "LOCAL_FALCON_API_KEY" if allow_global else None


def _profile_specific_api_key_env(profile: str) -> str:
    normalized = "".join(char if char.isalnum() else "_" for char in profile.upper()).strip("_")
    return f"LOCAL_FALCON_API_KEY_{normalized}"


def _local_falcon_config_api_key_env(profile: str) -> str:
    path = ROOT / "local" / profile / "local-falcon" / "config.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    value = payload.get("api_key_env")
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if _is_env_var_name(value) else ""


def _profile_from_manifest(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    profile = payload.get("profile")
    return profile.strip() if isinstance(profile, str) and profile.strip() else None


def _is_env_var_name(value: str) -> bool:
    return bool(value) and value.replace("_", "A").isalnum() and not value[0].isdigit()


if __name__ == "__main__":
    raise SystemExit(main())
