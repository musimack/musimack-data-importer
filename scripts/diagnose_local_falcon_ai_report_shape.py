from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_falcon_ai_diagnostic import diagnose_ai_report_shape, diagnostic_to_dict
from src.local_falcon_api_live_transport import LocalFalconLiveTransportError, LocalFalconReadOnlyLiveTransport
from src.local_falcon_api_plan import LocalFalconApiPlanError, build_manifest_plan


DEFAULT_MANIFEST = Path("local-falcon-manifests") / "aluma-local-ai-visibility.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely inspect Local Falcon AI report response shapes without printing raw payloads."
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Ignored manifest containing AI report ids.")
    parser.add_argument("--snapshot", help="Optional ignored shape-only JSON output path.")
    parser.add_argument("--max-samples", type=int, default=20, help="Maximum safe sample shapes per AI report.")
    args = parser.parse_args()

    try:
        plan = build_manifest_plan(Path(args.manifest), dry_run=True, no_write=True)
        reports = [report for report in plan.reports if report.query_type == "ai_visibility_prompt"]
        if not reports:
            raise LocalFalconApiPlanError("manifest does not contain AI visibility prompt reports")
        transport = LocalFalconReadOnlyLiveTransport.from_env()
        diagnostics = []
        for report in reports:
            payload = transport.get_report_summary(report.report_id)
            diagnostics.append(diagnostic_to_dict(diagnose_ai_report_shape(payload, report, max_samples=args.max_samples)))
    except (LocalFalconApiPlanError, LocalFalconLiveTransportError, OSError) as exc:
        print(f"Local Falcon AI diagnostic failed safely: {exc}", file=sys.stderr)
        return 1

    _print_diagnostics(diagnostics)
    if args.snapshot:
        try:
            snapshot_path = Path(args.snapshot)
            _ensure_safe_snapshot_path(snapshot_path)
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps({"reports": diagnostics}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print("")
            print(f"Shape-only snapshot written: {snapshot_path}")
        except OSError as exc:
            print(f"Local Falcon AI diagnostic snapshot failed safely: {exc}", file=sys.stderr)
            return 1
    return 0


def _print_diagnostics(diagnostics: list[dict]) -> None:
    print("Local Falcon AI raw point semantics diagnostic")
    print("Output is shape-only. Real values are redacted and raw payloads are not printed.")
    for index, item in enumerate(diagnostics, start=1):
        print("")
        print(f"{index}. Source: {item['source_label']}")
        print(f"   Query type: {item['query_type']}")
        print(f"   Scan kind: {item['scan_kind']}")
        print(f"   Report ID: {item['report_id_redacted']}")
        print(f"   Total point-like objects: {item['total_point_like_objects']}")
        print(f"   Nested result-bearing point count: {item['nested_result_bearing_point_count']}")
        print(f"   Points with numeric values: {item['points_with_numeric_values']}")
        print(f"   Points with string labels: {item['points_with_string_labels']}")
        print(f"   Points with observation sequence fields: {item['points_with_observation_sequence_fields']}")
        print(f"   Points with rank or position fields: {item['points_with_rank_or_position_fields']}")
        print(f"   Points with observed/mentioned/found fields: {item['points_with_observed_mentioned_found_fields']}")
        _print_paths("Candidate AI marker value paths", item["candidate_marker_value_paths"])
        _print_paths("Candidate brand/provider paths", item["candidate_brand_provider_paths"])
        _print_paths("Candidate sentiment paths", item["candidate_sentiment_paths"])
        _print_paths("Candidate phrase paths", item["candidate_phrase_paths"])
        _print_paths("Candidate SAIV/share paths", item["candidate_saiv_paths"])
        print("   Safe sample shapes:")
        for sample in item["safe_sample_shapes"][:10]:
            print(f"   - {json.dumps(sample, sort_keys=True)}")


def _print_paths(label: str, paths: list[str]) -> None:
    print(f"   {label}:")
    if not paths:
        print("   - [none found]")
        return
    for path in paths[:12]:
        print(f"   - {path}")
    if len(paths) > 12:
        print(f"   - ... {len(paths) - 12} more")


def _ensure_safe_snapshot_path(path: Path) -> None:
    normalized = path.as_posix()
    if not normalized.startswith(".test-tmp-"):
        raise OSError("diagnostic snapshots must be written under an ignored .test-tmp-* path")


if __name__ == "__main__":
    raise SystemExit(main())
