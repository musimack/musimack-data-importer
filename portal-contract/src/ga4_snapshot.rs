use serde::Serialize;
use serde_json::Value;
use thiserror::Error;

use crate::{
    ga4_oauth::GA4_PROVIDER,
    ga4_reporting::{
        Ga4ReportingDateRange, Ga4ReportingDimensionRow, Ga4ReportingMetric, Ga4ReportingResult,
    },
};

pub const GA4_SNAPSHOT_SCHEMA_VERSION: &str = "ga4_snapshot.v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Ga4SnapshotSource {
    Stub,
    Test,
    FutureLive,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum Ga4SnapshotTransformError {
    #[error("GA4 reporting result provider is unsupported")]
    UnsupportedProvider,
    #[error("GA4 reporting result property resource is invalid")]
    InvalidPropertyResource,
    #[error("GA4 reporting result contains invalid metric data")]
    InvalidMetric,
    #[error("GA4 reporting result contains invalid dimension row data")]
    InvalidDimensionRow,
    #[error("GA4 reporting result summary is required")]
    MissingSummary,
    #[error("GA4 snapshot payload serialization failed")]
    SerializationFailed,
}

#[derive(Debug, Serialize)]
struct Ga4SnapshotPayload<'a> {
    schema_version: &'static str,
    provider: &'static str,
    provider_key: &'a str,
    report_type: &'static str,
    property_resource: &'a str,
    date_range: SnapshotDateRange,
    comparison_date_range: Option<SnapshotDateRange>,
    source: Ga4SnapshotSource,
    summary: &'a str,
    metrics: Vec<SnapshotMetric<'a>>,
    dimension_rows: Vec<SnapshotDimensionRow<'a>>,
    summary_counts: SnapshotSummaryCounts,
    warnings: Vec<String>,
}

#[derive(Debug, Serialize)]
struct SnapshotDateRange {
    start: String,
    end: String,
}

#[derive(Debug, Serialize)]
struct SnapshotMetric<'a> {
    name: &'a str,
    value: f64,
    unit: &'a str,
}

#[derive(Debug, Serialize)]
struct SnapshotDimensionRow<'a> {
    label: &'a str,
    metrics: Vec<SnapshotMetric<'a>>,
}

#[derive(Debug, Serialize)]
struct SnapshotSummaryCounts {
    metric_count: usize,
    dimension_row_count: usize,
}

pub fn transform_ga4_reporting_result_to_snapshot_payload(
    result: &Ga4ReportingResult,
    source: Ga4SnapshotSource,
) -> Result<Value, Ga4SnapshotTransformError> {
    validate_result(result)?;

    let payload = Ga4SnapshotPayload {
        schema_version: GA4_SNAPSHOT_SCHEMA_VERSION,
        provider: "ga4",
        provider_key: GA4_PROVIDER,
        report_type: result.report_type.as_str(),
        property_resource: result.property_resource_id.trim(),
        date_range: snapshot_date_range(result.date_range),
        comparison_date_range: None,
        source,
        summary: result.summary.trim(),
        metrics: result.metrics.iter().map(snapshot_metric).collect(),
        dimension_rows: result.rows.iter().map(snapshot_dimension_row).collect(),
        summary_counts: SnapshotSummaryCounts {
            metric_count: result.metrics.len(),
            dimension_row_count: result.rows.len(),
        },
        warnings: Vec::new(),
    };

    serde_json::to_value(payload).map_err(|_| Ga4SnapshotTransformError::SerializationFailed)
}

fn validate_result(result: &Ga4ReportingResult) -> Result<(), Ga4SnapshotTransformError> {
    if result.provider != GA4_PROVIDER {
        return Err(Ga4SnapshotTransformError::UnsupportedProvider);
    }
    validate_property_resource_id(&result.property_resource_id)?;
    if result.summary.trim().is_empty() {
        return Err(Ga4SnapshotTransformError::MissingSummary);
    }
    for metric in &result.metrics {
        validate_metric(metric)?;
    }
    for row in &result.rows {
        validate_dimension_row(row)?;
    }
    Ok(())
}

fn validate_property_resource_id(value: &str) -> Result<(), Ga4SnapshotTransformError> {
    let Some(id) = value.trim().strip_prefix("properties/") else {
        return Err(Ga4SnapshotTransformError::InvalidPropertyResource);
    };
    if id.trim().is_empty() || !id.chars().all(|character| character.is_ascii_digit()) {
        return Err(Ga4SnapshotTransformError::InvalidPropertyResource);
    }
    Ok(())
}

fn validate_metric(metric: &Ga4ReportingMetric) -> Result<(), Ga4SnapshotTransformError> {
    if metric.name.trim().is_empty() || metric.unit.trim().is_empty() || !metric.value.is_finite() {
        return Err(Ga4SnapshotTransformError::InvalidMetric);
    }
    Ok(())
}

fn validate_dimension_row(row: &Ga4ReportingDimensionRow) -> Result<(), Ga4SnapshotTransformError> {
    if row.label.trim().is_empty() {
        return Err(Ga4SnapshotTransformError::InvalidDimensionRow);
    }
    for metric in &row.metrics {
        validate_metric(metric)?;
    }
    Ok(())
}

fn snapshot_date_range(range: Ga4ReportingDateRange) -> SnapshotDateRange {
    SnapshotDateRange {
        start: range.start().to_string(),
        end: range.end().to_string(),
    }
}

fn snapshot_metric(metric: &Ga4ReportingMetric) -> SnapshotMetric<'_> {
    SnapshotMetric {
        name: metric.name.trim(),
        value: metric.value,
        unit: metric.unit.trim(),
    }
}

fn snapshot_dimension_row(row: &Ga4ReportingDimensionRow) -> SnapshotDimensionRow<'_> {
    SnapshotDimensionRow {
        label: row.label.trim(),
        metrics: row.metrics.iter().map(snapshot_metric).collect(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveDate;
    use uuid::Uuid;

    use crate::ga4_reporting::{
        Ga4ReportType, Ga4ReportingQueryClient, Ga4ReportingQueryRequest,
        StubGa4ReportingQueryClient,
    };

    fn date(year: i32, month: u32, day: u32) -> NaiveDate {
        NaiveDate::from_ymd_opt(year, month, day).expect("test date")
    }

    fn query(report_type: Ga4ReportType) -> Ga4ReportingQueryRequest {
        Ga4ReportingQueryRequest::new(
            Some(Uuid::nil()),
            "properties/123456789",
            Ga4ReportingDateRange::new(date(2026, 4, 1), date(2026, 4, 30)).expect("date range"),
            None,
            report_type,
        )
        .expect("query")
    }

    fn stub_result(report_type: Ga4ReportType) -> Ga4ReportingResult {
        StubGa4ReportingQueryClient
            .run_report(&query(report_type))
            .expect("stub result")
    }

    #[test]
    fn traffic_overview_transforms_into_versioned_snapshot_payload() {
        let result = stub_result(Ga4ReportType::TrafficOverview);
        let payload =
            transform_ga4_reporting_result_to_snapshot_payload(&result, Ga4SnapshotSource::Stub)
                .expect("payload");

        assert_base_payload(&payload, "traffic_overview", "stub");
        assert_eq!(payload["metrics"][0]["name"], "users");
        assert_eq!(payload["summary_counts"]["metric_count"], 5);
        assert_eq!(payload["summary_counts"]["dimension_row_count"], 0);
    }

    #[test]
    fn channel_breakdown_transforms_into_versioned_snapshot_payload() {
        let result = stub_result(Ga4ReportType::ChannelBreakdown);
        let payload =
            transform_ga4_reporting_result_to_snapshot_payload(&result, Ga4SnapshotSource::Stub)
                .expect("payload");

        assert_base_payload(&payload, "channel_breakdown", "stub");
        assert_eq!(payload["dimension_rows"][0]["label"], "Organic Search");
    }

    #[test]
    fn top_pages_transforms_into_versioned_snapshot_payload() {
        let result = stub_result(Ga4ReportType::TopPages);
        let payload =
            transform_ga4_reporting_result_to_snapshot_payload(&result, Ga4SnapshotSource::Stub)
                .expect("payload");

        assert_base_payload(&payload, "top_pages", "stub");
        assert_eq!(payload["dimension_rows"][0]["label"], "/services");
    }

    #[test]
    fn conversions_summary_transforms_into_versioned_snapshot_payload() {
        let result = stub_result(Ga4ReportType::ConversionsSummary);
        let payload =
            transform_ga4_reporting_result_to_snapshot_payload(&result, Ga4SnapshotSource::Test)
                .expect("payload");

        assert_base_payload(&payload, "conversions_summary", "test");
        assert_eq!(payload["source"], "test");
        assert!(
            payload["metrics"]
                .as_array()
                .expect("metrics")
                .iter()
                .any(|metric| metric["name"] == "conversions")
        );
    }

    #[test]
    fn payload_does_not_include_secret_or_raw_provider_fields() {
        let result = stub_result(Ga4ReportType::TrafficOverview);
        let payload =
            transform_ga4_reporting_result_to_snapshot_payload(&result, Ga4SnapshotSource::Stub)
                .expect("payload");
        let text = payload.to_string();

        for forbidden in [
            "credentials_ref",
            "encrypted_payload",
            "credential_kind",
            "encryption_key_version",
            "scopes",
            "access_token",
            "refresh_token",
            "id_token",
            "api_key",
            "service_account",
            "authorization_code",
            "raw_provider",
            "google_response",
            "secret",
            "stack_trace",
        ] {
            assert!(
                !text.contains(forbidden),
                "forbidden field leaked into snapshot payload: {forbidden}"
            );
        }
    }

    #[test]
    fn unsupported_or_invalid_result_shapes_fail_safely() {
        let mut wrong_provider = stub_result(Ga4ReportType::TrafficOverview);
        wrong_provider.provider = "quickbooks".to_string();
        assert_eq!(
            transform_ga4_reporting_result_to_snapshot_payload(
                &wrong_provider,
                Ga4SnapshotSource::Stub
            )
            .unwrap_err(),
            Ga4SnapshotTransformError::UnsupportedProvider
        );

        let mut invalid_property = stub_result(Ga4ReportType::TrafficOverview);
        invalid_property.property_resource_id = "accounts/123".to_string();
        assert_eq!(
            transform_ga4_reporting_result_to_snapshot_payload(
                &invalid_property,
                Ga4SnapshotSource::Stub
            )
            .unwrap_err(),
            Ga4SnapshotTransformError::InvalidPropertyResource
        );

        let mut invalid_metric = stub_result(Ga4ReportType::TrafficOverview);
        invalid_metric.metrics[0].value = f64::NAN;
        assert_eq!(
            transform_ga4_reporting_result_to_snapshot_payload(
                &invalid_metric,
                Ga4SnapshotSource::Stub
            )
            .unwrap_err(),
            Ga4SnapshotTransformError::InvalidMetric
        );
    }

    #[test]
    fn transformer_is_pure_and_does_not_require_credentials_or_writes() {
        let result = stub_result(Ga4ReportType::TrafficOverview);
        let payload =
            transform_ga4_reporting_result_to_snapshot_payload(&result, Ga4SnapshotSource::Stub)
                .expect("payload without credentials or database");

        assert_eq!(payload["source"], "stub");
        assert_eq!(payload["warnings"].as_array().expect("warnings").len(), 0);
    }

    fn assert_base_payload(payload: &Value, report_type: &str, source: &str) {
        assert_eq!(payload["schema_version"], GA4_SNAPSHOT_SCHEMA_VERSION);
        assert_eq!(payload["provider"], "ga4");
        assert_eq!(payload["provider_key"], GA4_PROVIDER);
        assert_eq!(payload["report_type"], report_type);
        assert_eq!(payload["property_resource"], "properties/123456789");
        assert_eq!(payload["date_range"]["start"], "2026-04-01");
        assert_eq!(payload["date_range"]["end"], "2026-04-30");
        assert_eq!(payload["source"], source);
        assert!(payload["metrics"].is_array());
        assert!(payload["dimension_rows"].is_array());
    }
}
