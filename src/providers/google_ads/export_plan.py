from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import GoogleAdsReadiness


QUERY_AREAS = ("campaign", "keyword", "search term", "landing page", "time series", "budget pacing")


@dataclass(frozen=True)
class GoogleAdsExportPlan:
    profile: str
    start_date: str
    end_date: str
    granularity: str
    output_path: Path
    real_output: bool
    readiness: GoogleAdsReadiness
    validation_command: str

    def safe_lines(self) -> list[str]:
        missing = ", ".join(self.readiness.missing) if self.readiness.missing else "none"
        present = ", ".join(self.readiness.present) if self.readiness.present else "none"
        return [
            "Google Ads API export dry run only.",
            "No API calls were made.",
            "No files were written.",
            f"Profile: {self.profile}",
            f"Date range: {self.start_date} to {self.end_date}",
            f"Granularity: {self.granularity}",
            f"Future output: {self.output_path}",
            f"Real output flag provided: {'yes' if self.real_output else 'no'}",
            f"Credential readiness: {'ready' if self.readiness.ready else 'missing ' + missing}",
            f"Present credential/config env vars: {present}",
            f"Customer ID source: {self.readiness.customer_id_source}",
            f"Login customer ID present: {'yes' if self.readiness.has_login_customer_id else 'no'}",
            f"Query areas: {', '.join(QUERY_AREAS)}",
            f"Future validation: {self.validation_command}",
        ]


def build_google_ads_export_plan(
    *,
    profile: str,
    start_date: str,
    end_date: str,
    granularity: str,
    output_root: Path,
    real_output: bool,
    readiness: GoogleAdsReadiness,
) -> GoogleAdsExportPlan:
    output_path = output_root / profile / "google-ads-summary.json"
    return GoogleAdsExportPlan(
        profile=profile,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        output_path=output_path,
        real_output=real_output,
        readiness=readiness,
        validation_command=f"python scripts/validate_google_ads_summary.py --input {output_path}",
    )
