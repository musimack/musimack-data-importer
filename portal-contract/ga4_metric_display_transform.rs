use chrono::NaiveDate;
use serde_json::Value;
use thiserror::Error;

use crate::ga4_metric_display::{
    Ga4CompactList, Ga4CompactListRow, Ga4CompactMetric, Ga4DisplayAvailability,
    Ga4DisplayEmptyState, Ga4DisplayValue, Ga4DisplayValueKind, Ga4LineTrend, Ga4MetricCard,
    Ga4MetricComparison, Ga4MetricDisplayDateRange, Ga4MetricDisplayPayload,
    Ga4MetricDisplayValidationError, Ga4TrendPoint,
};
use crate::ga4_oauth::GA4_PROVIDER;
use crate::ga4_reporting::Ga4ReportType;
use crate::ga4_snapshot::GA4_SNAPSHOT_SCHEMA_VERSION;

const SNAPSHOT_PROVIDER_LABEL: &str = "ga4";
const MAX_LIST_ROWS: usize = 10;

#[derive(Debug, Error, PartialEq, Eq)]
pub enum Ga4MetricDisplayTransformError {
    #[error("GA4 snapshot display transform requires a JSON object")]
    InvalidPayload,
    #[error("GA4 snapshot display transform found an unsupported schema version")]
    InvalidSchemaVersion,
    #[error("GA4 snapshot display transform found an unsupported provider")]
    InvalidProvider,
    #[error("GA4 snapshot display transform found an unsupported report type")]
    UnsupportedReportType,
    #[error("GA4 snapshot display transform found an invalid date range")]
    InvalidDateRange,
    #[error("GA4 snapshot display transform found malformed metric data")]
    InvalidMetrics,
    #[error("GA4 snapshot display transform found malformed dimension row data")]
    InvalidDimensionRows,
    #[error("GA4 snapshot display transform found unsafe internal fields")]
    UnsafePayload,
    #[error("GA4 snapshot display transform produced invalid display data")]
    InvalidDisplayData,
}

impl From<Ga4MetricDisplayValidationError> for Ga4MetricDisplayTransformError {
    fn from(_: Ga4MetricDisplayValidationError) -> Self {
        Self::InvalidDisplayData
    }
}

pub fn transform_ga4_snapshot_to_metric_display(
    snapshot: &Value,
) -> Result<Ga4MetricDisplayPayload, Ga4MetricDisplayTransformError> {
    reject_forbidden_fields(snapshot)?;

    let object = snapshot
        .as_object()
        .ok_or(Ga4MetricDisplayTransformError::InvalidPayload)?;

    expect_string(object.get("schema_version"), GA4_SNAPSHOT_SCHEMA_VERSION)
        .map_err(|_| Ga4MetricDisplayTransformError::InvalidSchemaVersion)?;
    expect_string(object.get("provider"), SNAPSHOT_PROVIDER_LABEL)
        .map_err(|_| Ga4MetricDisplayTransformError::InvalidProvider)?;
    expect_string(object.get("provider_key"), GA4_PROVIDER)
        .map_err(|_| Ga4MetricDisplayTransformError::InvalidProvider)?;

    let report_type_text = object
        .get("report_type")
        .and_then(Value::as_str)
        .ok_or(Ga4MetricDisplayTransformError::UnsupportedReportType)?;
    let report_type = Ga4ReportType::parse(report_type_text)
        .map_err(|_| Ga4MetricDisplayTransformError::UnsupportedReportType)?;

    let date_range = parse_date_range(object.get("date_range"))?;
    let mut payload = Ga4MetricDisplayPayload::new(date_range);
    payload.comparison_range = parse_optional_date_range(object.get("comparison_date_range"))?;

    let metrics = parse_metrics(object.get("metrics"))?;
    let previous_metrics = parse_optional_metrics(object.get("previous_metrics"))?;
    payload.cards = build_cards(&metrics, &previous_metrics)?;
    payload.trends = build_users_and_sessions_trends(snapshot)?;
    payload.lists = build_lists(report_type, object.get("dimension_rows"))?;

    if !payload.has_display_content() {
        payload.empty_state = Some(Ga4DisplayEmptyState::new(
            "GA4 display data is not available for this period yet.",
        )?);
    }

    payload.validate()?;
    Ok(payload)
}

fn expect_string(value: Option<&Value>, expected: &str) -> Result<(), ()> {
    match value.and_then(Value::as_str) {
        Some(actual) if actual == expected => Ok(()),
        _ => Err(()),
    }
}

fn parse_date_range(
    value: Option<&Value>,
) -> Result<Ga4MetricDisplayDateRange, Ga4MetricDisplayTransformError> {
    let object = value
        .and_then(Value::as_object)
        .ok_or(Ga4MetricDisplayTransformError::InvalidDateRange)?;
    let start = parse_date(object.get("start"))?;
    let end = parse_date(object.get("end"))?;
    let label = format!("{start} through {end}");
    Ga4MetricDisplayDateRange::new(label, start, end)
        .map_err(|_| Ga4MetricDisplayTransformError::InvalidDateRange)
}

fn parse_optional_date_range(
    value: Option<&Value>,
) -> Result<Option<Ga4MetricDisplayDateRange>, Ga4MetricDisplayTransformError> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(value) => parse_date_range(Some(value)).map(Some),
    }
}

fn parse_date(value: Option<&Value>) -> Result<NaiveDate, Ga4MetricDisplayTransformError> {
    let text = value
        .and_then(Value::as_str)
        .ok_or(Ga4MetricDisplayTransformError::InvalidDateRange)?;
    NaiveDate::parse_from_str(text, "%Y-%m-%d")
        .map_err(|_| Ga4MetricDisplayTransformError::InvalidDateRange)
}

#[derive(Debug, Clone, Copy)]
struct SnapshotMetric<'a> {
    name: &'a str,
    value: f64,
    unit: &'a str,
}

fn parse_metrics(
    value: Option<&Value>,
) -> Result<Vec<SnapshotMetric<'_>>, Ga4MetricDisplayTransformError> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let rows = value
        .as_array()
        .ok_or(Ga4MetricDisplayTransformError::InvalidMetrics)?;
    rows.iter()
        .map(|row| {
            let object = row
                .as_object()
                .ok_or(Ga4MetricDisplayTransformError::InvalidMetrics)?;
            let name = object
                .get("name")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .ok_or(Ga4MetricDisplayTransformError::InvalidMetrics)?;
            let unit = object
                .get("unit")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .ok_or(Ga4MetricDisplayTransformError::InvalidMetrics)?;
            let value = object
                .get("value")
                .and_then(Value::as_f64)
                .filter(|value| value.is_finite())
                .ok_or(Ga4MetricDisplayTransformError::InvalidMetrics)?;
            Ok(SnapshotMetric { name, value, unit })
        })
        .collect()
}

fn parse_optional_metrics(
    value: Option<&Value>,
) -> Result<Vec<SnapshotMetric<'_>>, Ga4MetricDisplayTransformError> {
    match value {
        None | Some(Value::Null) => Ok(Vec::new()),
        Some(_) => parse_metrics(value),
    }
}

fn build_cards(
    metrics: &[SnapshotMetric<'_>],
    previous_metrics: &[SnapshotMetric<'_>],
) -> Result<Vec<Ga4MetricCard>, Ga4MetricDisplayTransformError> {
    let mut cards = Vec::new();

    for definition in CARD_DEFINITIONS {
        if let Some(metric) = metrics
            .iter()
            .find(|metric| metric.name == definition.snapshot_name)
        {
            let previous_metric = previous_metrics
                .iter()
                .find(|previous| previous.name == definition.snapshot_name)
                .copied();
            cards.push(build_card(definition, *metric, previous_metric)?);
        }
    }

    Ok(cards)
}

fn build_card(
    definition: &CardDefinition,
    metric: SnapshotMetric<'_>,
    previous_metric: Option<SnapshotMetric<'_>>,
) -> Result<Ga4MetricCard, Ga4MetricDisplayTransformError> {
    let (value, formatted_value, comparable_value) = display_value_for_metric(definition, metric);

    let availability = match &value {
        Ga4DisplayValue::Integer(0)
        | Ga4DisplayValue::DurationSeconds(0)
        | Ga4DisplayValue::Percentage(0.0) => Ga4DisplayAvailability::Zero,
        _ => Ga4DisplayAvailability::Available,
    };

    let mut card = Ga4MetricCard::new(
        definition.key,
        definition.label,
        value,
        formatted_value,
        availability,
    )
    .map_err(Ga4MetricDisplayTransformError::from)?;
    if let Some(previous_metric) = previous_metric {
        card.comparison = Some(build_comparison(
            definition,
            comparable_value,
            previous_metric,
        )?);
    }
    card.validate()?;
    Ok(card)
}

fn display_value_for_metric(
    definition: &CardDefinition,
    metric: SnapshotMetric<'_>,
) -> (Ga4DisplayValue, String, f64) {
    match definition.kind {
        CardValueKind::Count => {
            let count = metric.value.round() as i64;
            (
                Ga4DisplayValue::Integer(count),
                format_integer(count),
                count as f64,
            )
        }
        CardValueKind::Percentage => {
            let percent = normalized_percentage(metric);
            (
                Ga4DisplayValue::Percentage(round_one_decimal(percent)),
                format_percentage(percent),
                percent,
            )
        }
        CardValueKind::DurationSeconds => {
            let seconds = metric.value.round() as i64;
            (
                Ga4DisplayValue::DurationSeconds(seconds),
                format_duration_seconds(seconds),
                seconds as f64,
            )
        }
    }
}

fn build_comparison(
    definition: &CardDefinition,
    current_value: f64,
    previous_metric: SnapshotMetric<'_>,
) -> Result<Ga4MetricComparison, Ga4MetricDisplayTransformError> {
    let (previous_value, formatted_previous_value, previous_comparable) =
        display_value_for_metric(definition, previous_metric);
    let absolute_change = current_value - previous_comparable;
    let (absolute_value, formatted_absolute_change) =
        absolute_change_for_metric(definition, absolute_change);
    let percent_change = if previous_comparable == 0.0 {
        None
    } else {
        Some(round_one_decimal(
            (absolute_change / previous_comparable.abs()) * 100.0,
        ))
    };

    let comparison = Ga4MetricComparison {
        previous_value: Some(previous_value),
        formatted_previous_value: Some(formatted_previous_value),
        absolute_change: Some(absolute_value),
        formatted_absolute_change: Some(formatted_absolute_change),
        percent_change,
        direction: comparison_direction(absolute_change),
    };
    comparison.validate()?;
    Ok(comparison)
}

fn absolute_change_for_metric(
    definition: &CardDefinition,
    absolute_change: f64,
) -> (Ga4DisplayValue, String) {
    match definition.kind {
        CardValueKind::Count => {
            let change = absolute_change.round() as i64;
            (
                Ga4DisplayValue::Integer(change),
                format_signed_integer(change),
            )
        }
        CardValueKind::Percentage => {
            let change = round_one_decimal(absolute_change);
            (
                Ga4DisplayValue::Percentage(change),
                format_signed_percentage(change),
            )
        }
        CardValueKind::DurationSeconds => {
            let change = absolute_change.round() as i64;
            (
                Ga4DisplayValue::DurationSeconds(change),
                format_signed_duration_seconds(change),
            )
        }
    }
}

fn comparison_direction(absolute_change: f64) -> crate::ga4_metric_display::Ga4ComparisonDirection {
    if absolute_change.abs() < 0.000_001 {
        crate::ga4_metric_display::Ga4ComparisonDirection::Flat
    } else if absolute_change > 0.0 {
        crate::ga4_metric_display::Ga4ComparisonDirection::Up
    } else {
        crate::ga4_metric_display::Ga4ComparisonDirection::Down
    }
}

fn normalized_percentage(metric: SnapshotMetric<'_>) -> f64 {
    if metric.unit == "ratio" && metric.value.abs() <= 1.0 {
        metric.value * 100.0
    } else {
        metric.value
    }
}

#[derive(Debug)]
struct CardDefinition {
    snapshot_name: &'static str,
    key: &'static str,
    label: &'static str,
    kind: CardValueKind,
}

#[derive(Debug)]
enum CardValueKind {
    Count,
    Percentage,
    DurationSeconds,
}

const CARD_DEFINITIONS: &[CardDefinition] = &[
    CardDefinition {
        snapshot_name: "users",
        key: "users",
        label: "Users",
        kind: CardValueKind::Count,
    },
    CardDefinition {
        snapshot_name: "new_users",
        key: "new_users",
        label: "New Users",
        kind: CardValueKind::Count,
    },
    CardDefinition {
        snapshot_name: "sessions",
        key: "sessions",
        label: "Sessions",
        kind: CardValueKind::Count,
    },
    CardDefinition {
        snapshot_name: "engaged_sessions",
        key: "engaged_sessions",
        label: "Engaged Sessions",
        kind: CardValueKind::Count,
    },
    CardDefinition {
        snapshot_name: "engagement_rate",
        key: "engagement_rate",
        label: "Engagement Rate",
        kind: CardValueKind::Percentage,
    },
    CardDefinition {
        snapshot_name: "average_engagement_time_seconds",
        key: "average_engagement_time",
        label: "Average Engagement Time",
        kind: CardValueKind::DurationSeconds,
    },
    CardDefinition {
        snapshot_name: "average_engagement_time",
        key: "average_engagement_time",
        label: "Average Engagement Time",
        kind: CardValueKind::DurationSeconds,
    },
    CardDefinition {
        snapshot_name: "key_events",
        key: "key_events",
        label: "Key Events",
        kind: CardValueKind::Count,
    },
    CardDefinition {
        snapshot_name: "conversions",
        key: "conversions",
        label: "Conversions",
        kind: CardValueKind::Count,
    },
];

fn build_users_and_sessions_trends(
    snapshot: &Value,
) -> Result<Vec<Ga4LineTrend>, Ga4MetricDisplayTransformError> {
    let mut trends = Vec::new();

    if let Some(points) = parse_time_series_points(snapshot, "users")? {
        trends.push(Ga4LineTrend::new(
            "users_trend",
            "Users Over Time",
            Ga4DisplayValueKind::Integer,
            points,
            Ga4DisplayAvailability::Available,
        )?);
    }

    if let Some(points) = parse_time_series_points(snapshot, "sessions")? {
        trends.push(Ga4LineTrend::new(
            "sessions_trend",
            "Sessions Over Time",
            Ga4DisplayValueKind::Integer,
            points,
            Ga4DisplayAvailability::Available,
        )?);
    }

    if trends.is_empty() {
        trends.push(Ga4LineTrend::new(
            "users_trend",
            "Users Over Time",
            Ga4DisplayValueKind::Integer,
            Vec::new(),
            Ga4DisplayAvailability::Missing,
        )?);
    }

    Ok(trends)
}

fn parse_time_series_points(
    snapshot: &Value,
    metric_name: &str,
) -> Result<Option<Vec<Ga4TrendPoint>>, Ga4MetricDisplayTransformError> {
    let Some(series) = snapshot.get("time_series") else {
        return Ok(None);
    };
    let rows = series
        .as_array()
        .ok_or(Ga4MetricDisplayTransformError::InvalidMetrics)?;
    let mut points = Vec::new();

    for row in rows {
        let Some(object) = row.as_object() else {
            continue;
        };
        let Some(value) = object.get(metric_name).and_then(Value::as_f64) else {
            continue;
        };
        if !value.is_finite() {
            continue;
        }
        let Ok(date) = parse_date(object.get("date")) else {
            continue;
        };
        points.push(Ga4TrendPoint::new(date, value)?);
    }

    if points.is_empty() {
        Ok(None)
    } else {
        points.sort_by_key(|point| point.date);
        Ok(Some(points))
    }
}

fn build_lists(
    report_type: Ga4ReportType,
    dimension_rows: Option<&Value>,
) -> Result<Vec<Ga4CompactList>, Ga4MetricDisplayTransformError> {
    let Some((key, label)) = list_definition(report_type) else {
        return Ok(Vec::new());
    };

    let rows = parse_dimension_rows(dimension_rows)?;
    if rows.is_empty() {
        return Ok(vec![Ga4CompactList::new(
            key,
            label,
            Vec::new(),
            Ga4DisplayAvailability::Missing,
        )?]);
    }

    Ok(vec![Ga4CompactList::new(
        key,
        label,
        rows,
        Ga4DisplayAvailability::Available,
    )?])
}

fn list_definition(report_type: Ga4ReportType) -> Option<(&'static str, &'static str)> {
    match report_type {
        Ga4ReportType::ChannelBreakdown => Some(("traffic_channels", "Top Traffic Channels")),
        Ga4ReportType::TopPages => Some(("top_pages", "Top Pages")),
        _ => None,
    }
}

fn parse_dimension_rows(
    value: Option<&Value>,
) -> Result<Vec<Ga4CompactListRow>, Ga4MetricDisplayTransformError> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let rows = value
        .as_array()
        .ok_or(Ga4MetricDisplayTransformError::InvalidDimensionRows)?;

    rows.iter()
        .take(MAX_LIST_ROWS)
        .map(|row| {
            let object = row
                .as_object()
                .ok_or(Ga4MetricDisplayTransformError::InvalidDimensionRows)?;
            let label = object
                .get("label")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .ok_or(Ga4MetricDisplayTransformError::InvalidDimensionRows)?;
            let metrics = parse_metrics(object.get("metrics"))?
                .into_iter()
                .map(build_compact_metric)
                .collect::<Result<Vec<_>, _>>()?;

            Ga4CompactListRow::new(label, metrics).map_err(Into::into)
        })
        .collect()
}

fn build_compact_metric(
    metric: SnapshotMetric<'_>,
) -> Result<Ga4CompactMetric, Ga4MetricDisplayTransformError> {
    let (label, value, formatted_value) = match metric.name {
        "users" => {
            let count = metric.value.round() as i64;
            (
                "Users",
                Ga4DisplayValue::Integer(count),
                format_integer(count),
            )
        }
        "sessions" => {
            let count = metric.value.round() as i64;
            (
                "Sessions",
                Ga4DisplayValue::Integer(count),
                format_integer(count),
            )
        }
        "views" => {
            let count = metric.value.round() as i64;
            (
                "Views",
                Ga4DisplayValue::Integer(count),
                format_integer(count),
            )
        }
        "key_events" => {
            let count = metric.value.round() as i64;
            (
                "Key Events",
                Ga4DisplayValue::Integer(count),
                format_integer(count),
            )
        }
        "conversions" => {
            let count = metric.value.round() as i64;
            (
                "Conversions",
                Ga4DisplayValue::Integer(count),
                format_integer(count),
            )
        }
        "engagement_rate" => {
            let percent = if metric.unit == "ratio" && metric.value.abs() <= 1.0 {
                metric.value * 100.0
            } else {
                metric.value
            };
            (
                "Engagement Rate",
                Ga4DisplayValue::Percentage(round_one_decimal(percent)),
                format_percentage(percent),
            )
        }
        _ => {
            return Err(Ga4MetricDisplayTransformError::InvalidDimensionRows);
        }
    };

    Ga4CompactMetric::new(metric.name, label, value, formatted_value).map_err(Into::into)
}

fn reject_forbidden_fields(value: &Value) -> Result<(), Ga4MetricDisplayTransformError> {
    match value {
        Value::Object(object) => {
            for (key, nested) in object {
                if contains_forbidden_term(key) {
                    return Err(Ga4MetricDisplayTransformError::UnsafePayload);
                }
                reject_forbidden_fields(nested)?;
            }
        }
        Value::Array(values) => {
            for nested in values {
                reject_forbidden_fields(nested)?;
            }
        }
        Value::String(text) if contains_forbidden_term(text) => {
            return Err(Ga4MetricDisplayTransformError::UnsafePayload);
        }
        _ => {}
    }
    Ok(())
}

fn contains_forbidden_term(value: &str) -> bool {
    let normalized = value.to_ascii_lowercase();
    let normalized_words = normalized.replace([' ', '-'], "_");
    FORBIDDEN_TERMS
        .iter()
        .any(|forbidden| normalized.contains(forbidden) || normalized_words.contains(forbidden))
}

fn format_integer(value: i64) -> String {
    let sign = if value < 0 { "-" } else { "" };
    let digits = value.abs().to_string();
    let mut formatted = String::new();
    for (index, character) in digits.chars().rev().enumerate() {
        if index > 0 && index % 3 == 0 {
            formatted.push(',');
        }
        formatted.push(character);
    }
    let grouped: String = formatted.chars().rev().collect();
    format!("{sign}{grouped}")
}

fn format_signed_integer(value: i64) -> String {
    if value > 0 {
        format!("+{}", format_integer(value))
    } else {
        format_integer(value)
    }
}

fn format_percentage(value: f64) -> String {
    format!("{:.1}%", round_one_decimal(value))
}

fn format_signed_percentage(value: f64) -> String {
    let rounded = round_one_decimal(value);
    if rounded > 0.0 {
        format!("+{rounded:.1}%")
    } else {
        format!("{rounded:.1}%")
    }
}

fn round_one_decimal(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

fn format_duration_seconds(value: i64) -> String {
    let minutes = value / 60;
    let seconds = value % 60;
    if minutes > 0 {
        format!("{minutes}m {seconds:02}s")
    } else {
        format!("{seconds}s")
    }
}

fn format_signed_duration_seconds(value: i64) -> String {
    if value > 0 {
        format!("+{}", format_duration_seconds(value))
    } else if value < 0 {
        format!("-{}", format_duration_seconds(value.abs()))
    } else {
        format_duration_seconds(value)
    }
}

const FORBIDDEN_TERMS: &[&str] = &[
    "credential",
    "token",
    "secret",
    "encrypted",
    "refresh",
    "access_token",
    "source_snapshot",
    "provider_metadata",
    "raw_payload",
    "metrics_dump",
    "dimensions_dump",
    "oauth",
    "sync_run",
];

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn traffic_snapshot() -> Value {
        json!({
            "schema_version": "ga4_snapshot.v1",
            "provider": "ga4",
            "provider_key": "google_analytics",
            "report_type": "traffic_overview",
            "property_resource": "properties/123456789",
            "date_range": {
                "start": "2026-04-01",
                "end": "2026-04-30"
            },
            "comparison_date_range": null,
            "source": "test",
            "summary": "Sanitized GA4 traffic overview for local QA.",
            "metrics": [
                {"name": "users", "value": 1842.0, "unit": "count"},
                {"name": "new_users", "value": 1110.0, "unit": "count"},
                {"name": "sessions", "value": 2416.0, "unit": "count"},
                {"name": "engaged_sessions", "value": 1490.0, "unit": "count"},
                {"name": "engagement_rate", "value": 0.617, "unit": "ratio"},
                {"name": "average_engagement_time_seconds", "value": 83.0, "unit": "seconds"},
                {"name": "key_events", "value": 74.0, "unit": "count"}
            ],
            "dimension_rows": [],
            "summary_counts": {
                "metric_count": 7,
                "dimension_row_count": 0
            },
            "warnings": []
        })
    }

    fn add_time_series(snapshot: &mut Value) {
        snapshot["time_series"] = json!([
            {"date": "2026-04-01", "users": 54.0, "sessions": 72.0, "new_users": 32.0},
            {"date": "2026-04-02", "users": 61.0, "sessions": 80.0, "new_users": 37.0},
            {"date": "2026-04-03", "users": 58.0, "sessions": 76.0, "new_users": 34.0},
            {"date": "2026-04-04", "users": 69.0, "sessions": 91.0, "new_users": 43.0},
            {"date": "2026-04-05", "users": 72.0, "sessions": 95.0, "new_users": 44.0},
            {"date": "2026-04-06", "users": 66.0, "sessions": 88.0, "new_users": 39.0},
            {"date": "2026-04-07", "users": 81.0, "sessions": 108.0, "new_users": 50.0}
        ]);
    }

    fn add_previous_period(snapshot: &mut Value) {
        snapshot["comparison_date_range"] = json!({
            "start": "2026-03-01",
            "end": "2026-03-31"
        });
        snapshot["previous_metrics"] = json!([
            {"name": "users", "value": 1700.0, "unit": "count"},
            {"name": "new_users", "value": 1200.0, "unit": "count"},
            {"name": "sessions", "value": 2416.0, "unit": "count"},
            {"name": "engaged_sessions", "value": 1300.0, "unit": "count"},
            {"name": "engagement_rate", "value": 0.600, "unit": "ratio"},
            {"name": "average_engagement_time_seconds", "value": 70.0, "unit": "seconds"},
            {"name": "key_events", "value": 0.0, "unit": "count"}
        ]);
    }

    fn transform(value: &Value) -> Ga4MetricDisplayPayload {
        transform_ga4_snapshot_to_metric_display(value).expect("display payload")
    }

    #[test]
    fn valid_traffic_snapshot_transforms_into_metric_display_payload() {
        let payload = transform(&traffic_snapshot());

        assert_eq!(payload.schema_version, "ga4_metric_display.v1");
        assert_eq!(payload.provider, "ga4");
        assert_eq!(payload.date_range.start.to_string(), "2026-04-01");
        assert_eq!(payload.date_range.end.to_string(), "2026-04-30");
        assert_eq!(payload.cards.len(), 7);
        assert_eq!(payload.trends.len(), 1);
        assert_eq!(
            payload.trends[0].availability,
            Ga4DisplayAvailability::Missing
        );
        assert!(payload.lists.is_empty());
    }

    #[test]
    fn metric_cards_serialize_with_stable_keys_and_safe_labels() {
        let payload = transform(&traffic_snapshot());
        let cards = serde_json::to_value(&payload.cards).expect("cards json");

        assert_eq!(cards[0]["key"], "users");
        assert_eq!(cards[0]["label"], "Users");
        assert_eq!(cards[1]["key"], "new_users");
        assert_eq!(cards[1]["label"], "New Users");
        assert_eq!(cards[4]["key"], "engagement_rate");
        assert_eq!(cards[4]["label"], "Engagement Rate");
    }

    #[test]
    fn missing_metric_values_do_not_create_blank_cards() {
        let mut snapshot = traffic_snapshot();
        snapshot["metrics"] = json!([
            {"name": "sessions", "value": 2416.0, "unit": "count"}
        ]);

        let payload = transform(&snapshot);

        assert_eq!(payload.cards.len(), 1);
        assert_eq!(payload.cards[0].key, "sessions");
        assert_eq!(payload.cards[0].label, "Sessions");
    }

    #[test]
    fn zero_values_are_preserved_when_meaningful() {
        let mut snapshot = traffic_snapshot();
        snapshot["metrics"] = json!([
            {"name": "users", "value": 0.0, "unit": "count"},
            {"name": "sessions", "value": 0.0, "unit": "count"}
        ]);

        let payload = transform(&snapshot);
        let users = payload
            .cards
            .iter()
            .find(|card| card.key == "users")
            .expect("users card");

        assert_eq!(users.value, Ga4DisplayValue::Integer(0));
        assert_eq!(users.formatted_value, "0");
        assert_eq!(users.availability, Ga4DisplayAvailability::Zero);
    }

    #[test]
    fn percentage_and_duration_values_serialize_consistently() {
        let payload = transform(&traffic_snapshot());
        let value = serde_json::to_value(&payload).expect("payload json");
        let cards = value["cards"].as_array().expect("cards");

        let engagement_rate = cards
            .iter()
            .find(|card| card["key"] == "engagement_rate")
            .expect("engagement rate");
        assert_eq!(engagement_rate["value_kind"], "percentage");
        assert_eq!(engagement_rate["value"]["value"], 61.7);
        assert_eq!(engagement_rate["formatted_value"], "61.7%");

        let engagement_time = cards
            .iter()
            .find(|card| card["key"] == "average_engagement_time")
            .expect("engagement time");
        assert_eq!(engagement_time["value_kind"], "duration_seconds");
        assert_eq!(engagement_time["value"]["value"], 83);
        assert_eq!(engagement_time["formatted_value"], "1m 23s");
    }

    #[test]
    fn previous_period_values_create_safe_metric_card_comparisons() {
        let mut snapshot = traffic_snapshot();
        add_previous_period(&mut snapshot);

        let payload = transform(&snapshot);

        assert_eq!(
            payload
                .comparison_range
                .expect("comparison range")
                .start
                .to_string(),
            "2026-03-01"
        );

        let users = payload
            .cards
            .iter()
            .find(|card| card.key == "users")
            .expect("users card");
        let comparison = users.comparison.as_ref().expect("users comparison");
        assert_eq!(
            comparison.previous_value,
            Some(Ga4DisplayValue::Integer(1700))
        );
        assert_eq!(
            comparison.absolute_change,
            Some(Ga4DisplayValue::Integer(142))
        );
        assert_eq!(comparison.percent_change, Some(8.4));
        assert_eq!(
            comparison.direction,
            crate::ga4_metric_display::Ga4ComparisonDirection::Up
        );

        let new_users = payload
            .cards
            .iter()
            .find(|card| card.key == "new_users")
            .expect("new users card");
        assert_eq!(
            new_users
                .comparison
                .as_ref()
                .expect("new users comparison")
                .direction,
            crate::ga4_metric_display::Ga4ComparisonDirection::Down
        );

        let sessions = payload
            .cards
            .iter()
            .find(|card| card.key == "sessions")
            .expect("sessions card");
        assert_eq!(
            sessions
                .comparison
                .as_ref()
                .expect("sessions comparison")
                .direction,
            crate::ga4_metric_display::Ga4ComparisonDirection::Flat
        );
    }

    #[test]
    fn previous_zero_avoids_unsafe_percent_change() {
        let mut snapshot = traffic_snapshot();
        snapshot["previous_metrics"] = json!([
            {"name": "key_events", "value": 0.0, "unit": "count"}
        ]);

        let payload = transform(&snapshot);
        let key_events = payload
            .cards
            .iter()
            .find(|card| card.key == "key_events")
            .expect("key events card");
        let comparison = key_events.comparison.as_ref().expect("comparison");

        assert_eq!(comparison.previous_value, Some(Ga4DisplayValue::Integer(0)));
        assert_eq!(
            comparison.absolute_change,
            Some(Ga4DisplayValue::Integer(74))
        );
        assert!(comparison.percent_change.is_none());
        assert_eq!(
            comparison.direction,
            crate::ga4_metric_display::Ga4ComparisonDirection::Up
        );
    }

    #[test]
    fn missing_previous_values_do_not_create_misleading_comparisons() {
        let mut snapshot = traffic_snapshot();
        snapshot["previous_metrics"] = json!([
            {"name": "sessions", "value": 2000.0, "unit": "count"}
        ]);

        let payload = transform(&snapshot);

        let users = payload
            .cards
            .iter()
            .find(|card| card.key == "users")
            .expect("users card");
        assert!(users.comparison.is_none());

        let sessions = payload
            .cards
            .iter()
            .find(|card| card.key == "sessions")
            .expect("sessions card");
        assert!(sessions.comparison.is_some());
    }

    #[test]
    fn duration_and_percentage_metrics_compare_safely() {
        let mut snapshot = traffic_snapshot();
        add_previous_period(&mut snapshot);

        let payload = transform(&snapshot);
        let engagement_rate = payload
            .cards
            .iter()
            .find(|card| card.key == "engagement_rate")
            .expect("engagement rate");
        let rate_comparison = engagement_rate
            .comparison
            .as_ref()
            .expect("rate comparison");
        assert_eq!(
            rate_comparison.previous_value,
            Some(Ga4DisplayValue::Percentage(60.0))
        );
        assert_eq!(
            rate_comparison.absolute_change,
            Some(Ga4DisplayValue::Percentage(1.7))
        );
        assert_eq!(rate_comparison.percent_change, Some(2.8));

        let engagement_time = payload
            .cards
            .iter()
            .find(|card| card.key == "average_engagement_time")
            .expect("engagement time");
        let time_comparison = engagement_time
            .comparison
            .as_ref()
            .expect("time comparison");
        assert_eq!(
            time_comparison.previous_value,
            Some(Ga4DisplayValue::DurationSeconds(70))
        );
        assert_eq!(
            time_comparison.absolute_change,
            Some(Ga4DisplayValue::DurationSeconds(13))
        );
        assert_eq!(
            time_comparison.formatted_absolute_change.as_deref(),
            Some("+13s")
        );
    }

    #[test]
    fn line_trends_are_created_when_safe_time_series_points_exist() {
        let mut snapshot = traffic_snapshot();
        add_time_series(&mut snapshot);

        let payload = transform(&snapshot);

        assert_eq!(payload.trends.len(), 2);
        let users_trend = payload
            .trends
            .iter()
            .find(|trend| trend.key == "users_trend")
            .expect("users trend");
        let sessions_trend = payload
            .trends
            .iter()
            .find(|trend| trend.key == "sessions_trend")
            .expect("sessions trend");
        assert_eq!(users_trend.availability, Ga4DisplayAvailability::Available);
        assert_eq!(users_trend.points.len(), 7);
        assert_eq!(users_trend.points[0].date.to_string(), "2026-04-01");
        assert_eq!(users_trend.points[0].value, 54.0);
        assert_eq!(sessions_trend.points.len(), 7);
        assert_eq!(sessions_trend.points[0].value, 72.0);
    }

    #[test]
    fn sessions_line_trend_is_created_when_users_points_are_missing() {
        let mut snapshot = traffic_snapshot();
        snapshot["time_series"] = json!([
            {"date": "2026-04-01", "sessions": 72.0},
            {"date": "2026-04-02", "sessions": 80.0}
        ]);

        let payload = transform(&snapshot);

        assert_eq!(payload.trends.len(), 1);
        assert_eq!(payload.trends[0].key, "sessions_trend");
        assert_eq!(
            payload.trends[0].availability,
            Ga4DisplayAvailability::Available
        );
        assert_eq!(payload.trends[0].points[1].value, 80.0);
    }

    #[test]
    fn trend_points_are_sorted_by_date_for_predictable_display() {
        let mut snapshot = traffic_snapshot();
        snapshot["time_series"] = json!([
            {"date": "2026-04-03", "users": 58.0, "sessions": 76.0},
            {"date": "2026-04-01", "users": 54.0, "sessions": 72.0},
            {"date": "2026-04-02", "users": 61.0, "sessions": 80.0}
        ]);

        let payload = transform(&snapshot);
        let users_trend = payload
            .trends
            .iter()
            .find(|trend| trend.key == "users_trend")
            .expect("users trend");

        assert_eq!(users_trend.points[0].date.to_string(), "2026-04-01");
        assert_eq!(users_trend.points[1].date.to_string(), "2026-04-02");
        assert_eq!(users_trend.points[2].date.to_string(), "2026-04-03");
    }

    #[test]
    fn malformed_time_series_points_are_omitted_without_panic() {
        let mut snapshot = traffic_snapshot();
        snapshot["time_series"] = json!([
            {"date": "2026-04-01", "users": 54.0, "sessions": 72.0},
            {"date": "not-a-date", "users": 999.0, "sessions": 999.0},
            {"date": "2026-04-02", "users": "many", "sessions": 80.0},
            "not a point",
            {"date": "2026-04-03", "users": 58.0}
        ]);

        let payload = transform(&snapshot);
        let users_trend = payload
            .trends
            .iter()
            .find(|trend| trend.key == "users_trend")
            .expect("users trend");
        let sessions_trend = payload
            .trends
            .iter()
            .find(|trend| trend.key == "sessions_trend")
            .expect("sessions trend");

        assert_eq!(users_trend.points.len(), 2);
        assert_eq!(sessions_trend.points.len(), 2);
        assert_eq!(users_trend.points[1].date.to_string(), "2026-04-03");
        assert_eq!(sessions_trend.points[1].date.to_string(), "2026-04-02");
    }

    #[test]
    fn empty_time_series_creates_safe_missing_trend_state() {
        let mut snapshot = traffic_snapshot();
        snapshot["time_series"] = json!([]);

        let payload = transform(&snapshot);

        assert_eq!(payload.trends[0].key, "users_trend");
        assert_eq!(payload.trends[0].points.len(), 0);
        assert_eq!(
            payload.trends[0].availability,
            Ga4DisplayAvailability::Missing
        );
    }

    #[test]
    fn missing_time_series_creates_safe_missing_trend_state() {
        let payload = transform(&traffic_snapshot());

        assert_eq!(payload.trends[0].key, "users_trend");
        assert_eq!(payload.trends[0].points.len(), 0);
        assert_eq!(
            payload.trends[0].availability,
            Ga4DisplayAvailability::Missing
        );
    }

    #[test]
    fn channel_breakdown_snapshot_transforms_dimension_rows_into_compact_list() {
        let mut snapshot = traffic_snapshot();
        snapshot["report_type"] = json!("channel_breakdown");
        snapshot["metrics"] = json!([]);
        snapshot["dimension_rows"] = json!([
            {
                "label": "Organic Search",
                "metrics": [
                    {"name": "sessions", "value": 1044.0, "unit": "count"},
                    {"name": "key_events", "value": 31.0, "unit": "count"}
                ]
            }
        ]);

        let payload = transform(&snapshot);

        assert_eq!(payload.lists.len(), 1);
        assert_eq!(payload.lists[0].key, "traffic_channels");
        assert_eq!(payload.lists[0].label, "Top Traffic Channels");
        assert_eq!(payload.lists[0].rows[0].label, "Organic Search");
        assert_eq!(payload.lists[0].rows[0].metrics[0].key, "sessions");
    }

    #[test]
    fn unsupported_snapshot_report_types_return_typed_error() {
        let mut snapshot = traffic_snapshot();
        snapshot["report_type"] = json!("audience_explorer");

        assert_eq!(
            transform_ga4_snapshot_to_metric_display(&snapshot).unwrap_err(),
            Ga4MetricDisplayTransformError::UnsupportedReportType
        );
    }

    #[test]
    fn malformed_metric_values_return_typed_error() {
        let mut snapshot = traffic_snapshot();
        snapshot["metrics"] = json!([
            {"name": "users", "value": "many", "unit": "count"}
        ]);

        assert_eq!(
            transform_ga4_snapshot_to_metric_display(&snapshot).unwrap_err(),
            Ga4MetricDisplayTransformError::InvalidMetrics
        );
    }

    #[test]
    fn forbidden_source_or_secret_like_fields_are_rejected() {
        let mut snapshot = traffic_snapshot();
        snapshot["access_token"] = json!("not allowed");

        assert_eq!(
            transform_ga4_snapshot_to_metric_display(&snapshot).unwrap_err(),
            Ga4MetricDisplayTransformError::UnsafePayload
        );
    }

    #[test]
    fn serialized_transformer_output_does_not_contain_forbidden_field_names() {
        let payload = transform(&traffic_snapshot());
        let text = serde_json::to_string(&payload).expect("payload json");

        for forbidden in [
            "credential",
            "token",
            "secret",
            "encrypted",
            "refresh",
            "access_token",
            "source_snapshot",
            "provider_metadata",
            "raw_payload",
            "metrics_dump",
            "dimensions_dump",
        ] {
            assert!(
                !text.contains(forbidden),
                "forbidden field leaked into metric display payload: {forbidden}"
            );
        }
    }
}
