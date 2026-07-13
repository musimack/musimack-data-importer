from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client_report_ga4_exact_range_provider import EXACT_RANGE_KEYS
from src.client_report_ga4_exact_ranges import validate_ga4_exact_range_summary_contract
from src.client_report_presentation_ranges import resolve_range_key
from src.config import ConfigError, DateRange, load_ga4_config
from src.ga4_client import Ga4ClientError, Ga4DataClient
from src.profile_aliases import ProfileAliasError, resolve_profile_slug
from src.validate import validate_snapshot_payload


ENGAGEMENT_METRICS = ("engagementRate", "engagedSessions")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh only GA4 Engagement Rate and Engaged Sessions for the retained R1 source files."
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--report-start-date", required=True)
    parser.add_argument("--report-end-date", required=True)
    parser.add_argument("--real-output", action="store_true")
    args = parser.parse_args()

    try:
        profile = resolve_profile_slug(args.profile)
        if profile != "aluma-seo-geo" or not args.real_output:
            raise ConfigError("the controlled engagement refresh requires aluma-seo-geo and --real-output")
        report_start = date.fromisoformat(args.report_start_date)
        report_end = date.fromisoformat(args.report_end_date)
        if report_start > report_end:
            raise ConfigError("report start must be on or before report end")
        output_dir = Path("exports") / "local-real" / "dashboard-lab" / profile
        snapshot_path = output_dir / "ga4-snapshot.json"
        summary_path = output_dir / "ga4-summary.json"
        exact_path = output_dir / "ga4_metric_display_exact_ranges.v1.json"
        snapshot = _read_object(snapshot_path)
        summary = _read_object(summary_path)
        exact = _read_object(exact_path)

        client = Ga4DataClient(load_ga4_config(args.profile))
        report_metrics = _query(client, DateRange(report_start, report_end))
        _upsert_snapshot_metrics(snapshot, report_metrics)
        summary_metrics = summary.get("summary_metrics")
        if not isinstance(summary_metrics, dict):
            raise ValueError("GA4 dashboard summary metrics are missing")
        summary_metrics.update(report_metrics)

        ranges = exact.get("ranges")
        if not isinstance(ranges, list):
            raise ValueError("GA4 exact-range source ranges are missing")
        refreshed_ranges = 0
        for range_key in EXACT_RANGE_KEYS:
            resolved = resolve_range_key(range_key, report_end)
            entry = next(
                (
                    item
                    for item in ranges
                    if isinstance(item, dict)
                    and item.get("range_key") == range_key
                    and item.get("requested_start_date") == resolved.start_date.isoformat()
                    and item.get("requested_end_date") == resolved.end_date.isoformat()
                ),
                None,
            )
            if not isinstance(entry, dict) or not isinstance(entry.get("metrics"), dict):
                raise ValueError(f"GA4 exact-range entry is missing for {range_key}")
            entry["metrics"].update(_query(client, DateRange(resolved.start_date, resolved.end_date)))
            entry.setdefault("quality_notes", []).append(
                "Controlled R1 engagement refresh queried only Engagement Rate and Engaged Sessions."
            )
            refreshed_ranges += 1

        validate_snapshot_payload(snapshot)
        validate_ga4_exact_range_summary_contract(exact)
        _write_json(snapshot_path, snapshot)
        _write_json(summary_path, summary)
        _write_json(exact_path, exact)
    except (ConfigError, Ga4ClientError, ProfileAliasError, OSError, ValueError) as exc:
        print(f"Controlled GA4 engagement refresh failed safely: {exc}", file=sys.stderr)
        return 1

    print("Controlled GA4 engagement refresh completed.")
    print("Provider calls: 5; metrics: Engagement Rate, Engaged Sessions.")
    print(f"Exact ranges refreshed: {refreshed_ranges}.")
    print("Only sanitized ignored local-real source files were updated; no identifiers or credentials were printed.")
    return 0


def _query(client: Ga4DataClient, date_range: DateRange) -> dict[str, float | int]:
    response = client.run_exact_range_summary(date_range, metric_names=ENGAGEMENT_METRICS)
    headers = response.get("metricHeaders")
    rows = response.get("rows")
    if not isinstance(headers, list) or not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("GA4 engagement response must contain exactly one summary row")
    values = rows[0].get("metricValues") if isinstance(rows[0], dict) else None
    if not isinstance(values, list) or len(values) != len(headers):
        raise ValueError("GA4 engagement response metric values are incomplete")
    parsed: dict[str, float | int] = {}
    for header, value in zip(headers, values, strict=True):
        name = header.get("name") if isinstance(header, dict) else None
        raw = value.get("value") if isinstance(value, dict) else None
        if not isinstance(raw, str):
            raise ValueError("GA4 engagement response contains an invalid metric value")
        if name == "engagementRate":
            parsed["engagement_rate"] = float(raw)
        elif name == "engagedSessions":
            parsed["engaged_sessions"] = int(float(raw))
    if set(parsed) != {"engagement_rate", "engaged_sessions"}:
        raise ValueError("GA4 engagement response omitted an approved metric")
    return parsed


def _upsert_snapshot_metrics(snapshot: dict[str, Any], metrics: dict[str, float | int]) -> None:
    rows = snapshot.get("metrics")
    if not isinstance(rows, list):
        raise ValueError("GA4 snapshot metrics are missing")
    by_name = {row.get("name"): row for row in rows if isinstance(row, dict)}
    definitions = {
        "engagement_rate": "ratio",
        "engaged_sessions": "count",
    }
    for name, value in metrics.items():
        row = by_name.get(name)
        if isinstance(row, dict):
            row.update({"value": value, "unit": definitions[name]})
        else:
            rows.append({"name": name, "value": value, "unit": definitions[name]})


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
