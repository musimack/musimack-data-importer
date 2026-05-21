use chrono::NaiveDate;
use serde::Serialize;
use thiserror::Error;

pub const GA4_METRIC_DISPLAY_SCHEMA_VERSION: &str = "ga4_metric_display.v1";
pub const GA4_METRIC_DISPLAY_PROVIDER: &str = "ga4";

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Ga4MetricDisplayPayload {
    pub schema_version: &'static str,
    pub provider: &'static str,
    pub date_range: Ga4MetricDisplayDateRange,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub comparison_range: Option<Ga4MetricDisplayDateRange>,
    pub cards: Vec<Ga4MetricCard>,
    pub trends: Vec<Ga4LineTrend>,
    pub lists: Vec<Ga4CompactList>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub empty_state: Option<Ga4DisplayEmptyState>,
}

impl Ga4MetricDisplayPayload {
    pub fn new(date_range: Ga4MetricDisplayDateRange) -> Self {
        Self {
            schema_version: GA4_METRIC_DISPLAY_SCHEMA_VERSION,
            provider: GA4_METRIC_DISPLAY_PROVIDER,
            date_range,
            comparison_range: None,
            cards: Vec::new(),
            trends: Vec::new(),
            lists: Vec::new(),
            empty_state: None,
        }
    }

    pub fn empty(
        date_range: Ga4MetricDisplayDateRange,
        message: impl Into<String>,
    ) -> Result<Self, Ga4MetricDisplayValidationError> {
        let mut payload = Self::new(date_range);
        payload.empty_state = Some(Ga4DisplayEmptyState::new(message)?);
        Ok(payload)
    }

    pub fn has_display_content(&self) -> bool {
        !self.cards.is_empty() || !self.trends.is_empty() || !self.lists.is_empty()
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        self.date_range.validate()?;
        if let Some(range) = &self.comparison_range {
            range.validate()?;
        }
        for card in &self.cards {
            card.validate()?;
        }
        for trend in &self.trends {
            trend.validate()?;
        }
        for list in &self.lists {
            list.validate()?;
        }
        if let Some(empty_state) = &self.empty_state {
            empty_state.validate()?;
        }
        if !self.has_display_content() && self.empty_state.is_none() {
            return Err(Ga4MetricDisplayValidationError::MissingDisplayContent);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Ga4MetricDisplayDateRange {
    pub label: String,
    pub start: NaiveDate,
    pub end: NaiveDate,
}

impl Ga4MetricDisplayDateRange {
    pub fn new(
        label: impl Into<String>,
        start: NaiveDate,
        end: NaiveDate,
    ) -> Result<Self, Ga4MetricDisplayValidationError> {
        let range = Self {
            label: label.into(),
            start,
            end,
        };
        range.validate()?;
        Ok(range)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        validate_display_text(&self.label, 80)?;
        if self.end < self.start {
            return Err(Ga4MetricDisplayValidationError::InvalidDateRange);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Ga4MetricCard {
    pub key: String,
    pub label: String,
    pub value: Ga4DisplayValue,
    pub formatted_value: String,
    pub value_kind: Ga4DisplayValueKind,
    pub availability: Ga4DisplayAvailability,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub comparison: Option<Ga4MetricComparison>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub help_text: Option<String>,
}

impl Ga4MetricCard {
    pub fn new(
        key: impl Into<String>,
        label: impl Into<String>,
        value: Ga4DisplayValue,
        formatted_value: impl Into<String>,
        availability: Ga4DisplayAvailability,
    ) -> Result<Self, Ga4MetricDisplayValidationError> {
        let value_kind = value.kind();
        let card = Self {
            key: key.into(),
            label: label.into(),
            value,
            formatted_value: formatted_value.into(),
            value_kind,
            availability,
            comparison: None,
            help_text: None,
        };
        card.validate()?;
        Ok(card)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        validate_key(&self.key)?;
        validate_display_text(&self.label, 80)?;
        self.value.validate()?;
        validate_display_text(&self.formatted_value, 64)?;
        if self.value.kind() != self.value_kind {
            return Err(Ga4MetricDisplayValidationError::ValueKindMismatch);
        }
        if let Some(comparison) = &self.comparison {
            comparison.validate()?;
        }
        if let Some(help_text) = &self.help_text {
            validate_display_text(help_text, 220)?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Ga4MetricComparison {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub previous_value: Option<Ga4DisplayValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub formatted_previous_value: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub absolute_change: Option<Ga4DisplayValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub formatted_absolute_change: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub percent_change: Option<f64>,
    pub direction: Ga4ComparisonDirection,
}

impl Ga4MetricComparison {
    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        if let Some(value) = &self.previous_value {
            value.validate()?;
        }
        if let Some(value) = &self.absolute_change {
            value.validate()?;
        }
        if let Some(value) = self.percent_change
            && !value.is_finite()
        {
            return Err(Ga4MetricDisplayValidationError::InvalidNumber);
        }
        if let Some(value) = &self.formatted_previous_value {
            validate_display_text(value, 64)?;
        }
        if let Some(value) = &self.formatted_absolute_change {
            validate_display_text(value, 64)?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Ga4ComparisonDirection {
    Up,
    Down,
    Flat,
    NotAvailable,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Ga4LineTrend {
    pub key: String,
    pub label: String,
    pub value_kind: Ga4DisplayValueKind,
    pub availability: Ga4DisplayAvailability,
    pub points: Vec<Ga4TrendPoint>,
}

impl Ga4LineTrend {
    pub fn new(
        key: impl Into<String>,
        label: impl Into<String>,
        value_kind: Ga4DisplayValueKind,
        points: Vec<Ga4TrendPoint>,
        availability: Ga4DisplayAvailability,
    ) -> Result<Self, Ga4MetricDisplayValidationError> {
        let trend = Self {
            key: key.into(),
            label: label.into(),
            value_kind,
            availability,
            points,
        };
        trend.validate()?;
        Ok(trend)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        validate_key(&self.key)?;
        validate_display_text(&self.label, 100)?;
        for point in &self.points {
            point.validate()?;
        }
        if self.availability == Ga4DisplayAvailability::Available && self.points.is_empty() {
            return Err(Ga4MetricDisplayValidationError::MissingTrendPoints);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct Ga4TrendPoint {
    pub date: NaiveDate,
    pub value: f64,
}

impl Ga4TrendPoint {
    pub fn new(date: NaiveDate, value: f64) -> Result<Self, Ga4MetricDisplayValidationError> {
        let point = Self { date, value };
        point.validate()?;
        Ok(point)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        if !self.value.is_finite() {
            return Err(Ga4MetricDisplayValidationError::InvalidNumber);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Ga4CompactList {
    pub key: String,
    pub label: String,
    pub availability: Ga4DisplayAvailability,
    pub rows: Vec<Ga4CompactListRow>,
}

impl Ga4CompactList {
    pub fn new(
        key: impl Into<String>,
        label: impl Into<String>,
        rows: Vec<Ga4CompactListRow>,
        availability: Ga4DisplayAvailability,
    ) -> Result<Self, Ga4MetricDisplayValidationError> {
        let list = Self {
            key: key.into(),
            label: label.into(),
            availability,
            rows,
        };
        list.validate()?;
        Ok(list)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        validate_key(&self.key)?;
        validate_display_text(&self.label, 100)?;
        for row in &self.rows {
            row.validate()?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Ga4CompactListRow {
    pub label: String,
    pub metrics: Vec<Ga4CompactMetric>,
}

impl Ga4CompactListRow {
    pub fn new(
        label: impl Into<String>,
        metrics: Vec<Ga4CompactMetric>,
    ) -> Result<Self, Ga4MetricDisplayValidationError> {
        let row = Self {
            label: label.into(),
            metrics,
        };
        row.validate()?;
        Ok(row)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        validate_display_text(&self.label, 120)?;
        if self.metrics.is_empty() {
            return Err(Ga4MetricDisplayValidationError::MissingDisplayContent);
        }
        for metric in &self.metrics {
            metric.validate()?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Ga4CompactMetric {
    pub key: String,
    pub label: String,
    pub value: Ga4DisplayValue,
    pub formatted_value: String,
    pub value_kind: Ga4DisplayValueKind,
}

impl Ga4CompactMetric {
    pub fn new(
        key: impl Into<String>,
        label: impl Into<String>,
        value: Ga4DisplayValue,
        formatted_value: impl Into<String>,
    ) -> Result<Self, Ga4MetricDisplayValidationError> {
        let value_kind = value.kind();
        let metric = Self {
            key: key.into(),
            label: label.into(),
            value,
            formatted_value: formatted_value.into(),
            value_kind,
        };
        metric.validate()?;
        Ok(metric)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        validate_key(&self.key)?;
        validate_display_text(&self.label, 80)?;
        self.value.validate()?;
        validate_display_text(&self.formatted_value, 64)?;
        if self.value.kind() != self.value_kind {
            return Err(Ga4MetricDisplayValidationError::ValueKindMismatch);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum Ga4DisplayValue {
    Integer(i64),
    Decimal(f64),
    Percentage(f64),
    DurationSeconds(i64),
    Text(String),
}

impl Ga4DisplayValue {
    pub fn kind(&self) -> Ga4DisplayValueKind {
        match self {
            Self::Integer(_) => Ga4DisplayValueKind::Integer,
            Self::Decimal(_) => Ga4DisplayValueKind::Decimal,
            Self::Percentage(_) => Ga4DisplayValueKind::Percentage,
            Self::DurationSeconds(_) => Ga4DisplayValueKind::DurationSeconds,
            Self::Text(_) => Ga4DisplayValueKind::Text,
        }
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        match self {
            Self::Decimal(value) | Self::Percentage(value) if !value.is_finite() => {
                Err(Ga4MetricDisplayValidationError::InvalidNumber)
            }
            Self::Text(value) => validate_display_text(value, 120),
            _ => Ok(()),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Ga4DisplayValueKind {
    Integer,
    Decimal,
    Percentage,
    DurationSeconds,
    Text,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Ga4DisplayAvailability {
    Available,
    Zero,
    Missing,
    Sparse,
    Malformed,
    NotConfigured,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Ga4DisplayEmptyState {
    pub message: String,
    pub availability: Ga4DisplayAvailability,
}

impl Ga4DisplayEmptyState {
    pub fn new(message: impl Into<String>) -> Result<Self, Ga4MetricDisplayValidationError> {
        let empty_state = Self {
            message: message.into(),
            availability: Ga4DisplayAvailability::Missing,
        };
        empty_state.validate()?;
        Ok(empty_state)
    }

    pub fn validate(&self) -> Result<(), Ga4MetricDisplayValidationError> {
        validate_display_text(&self.message, 180)
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum Ga4MetricDisplayValidationError {
    #[error("GA4 metric display date range is invalid")]
    InvalidDateRange,
    #[error("GA4 metric display key is invalid")]
    InvalidKey,
    #[error("GA4 metric display text is invalid")]
    InvalidDisplayText,
    #[error("GA4 metric display value contains an invalid number")]
    InvalidNumber,
    #[error("GA4 metric display value kind does not match the value")]
    ValueKindMismatch,
    #[error("GA4 metric display payload has no display content")]
    MissingDisplayContent,
    #[error("GA4 metric display trend is missing points")]
    MissingTrendPoints,
}

fn validate_key(value: &str) -> Result<(), Ga4MetricDisplayValidationError> {
    let trimmed = value.trim();
    if trimmed.is_empty()
        || trimmed.len() > 80
        || !trimmed.chars().all(|character| {
            character.is_ascii_lowercase() || character.is_ascii_digit() || character == '_'
        })
        || contains_forbidden_term(trimmed)
    {
        return Err(Ga4MetricDisplayValidationError::InvalidKey);
    }
    Ok(())
}

fn validate_display_text(
    value: &str,
    max_len: usize,
) -> Result<(), Ga4MetricDisplayValidationError> {
    let trimmed = value.trim();
    if trimmed.is_empty() || trimmed.len() > max_len || contains_forbidden_term(trimmed) {
        return Err(Ga4MetricDisplayValidationError::InvalidDisplayText);
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
    use serde_json::Value;

    fn date(year: i32, month: u32, day: u32) -> NaiveDate {
        NaiveDate::from_ymd_opt(year, month, day).expect("test date")
    }

    fn april_range() -> Ga4MetricDisplayDateRange {
        Ga4MetricDisplayDateRange::new("April 2026", date(2026, 4, 1), date(2026, 4, 30))
            .expect("date range")
    }

    fn visitor_card() -> Ga4MetricCard {
        let mut card = Ga4MetricCard::new(
            "users",
            "Website Visitors",
            Ga4DisplayValue::Integer(1842),
            "1,842",
            Ga4DisplayAvailability::Available,
        )
        .expect("metric card");
        card.comparison = Some(Ga4MetricComparison {
            previous_value: Some(Ga4DisplayValue::Integer(1720)),
            formatted_previous_value: Some("1,720".to_string()),
            absolute_change: Some(Ga4DisplayValue::Integer(122)),
            formatted_absolute_change: Some("+122".to_string()),
            percent_change: Some(7.1),
            direction: Ga4ComparisonDirection::Up,
        });
        card
    }

    fn users_trend() -> Ga4LineTrend {
        Ga4LineTrend::new(
            "users_trend",
            "Website visitors over time",
            Ga4DisplayValueKind::Integer,
            vec![
                Ga4TrendPoint::new(date(2026, 4, 1), 54.0).expect("point"),
                Ga4TrendPoint::new(date(2026, 4, 2), 61.0).expect("point"),
            ],
            Ga4DisplayAvailability::Available,
        )
        .expect("trend")
    }

    #[test]
    fn metric_display_payload_serializes_with_expected_schema_version() {
        let mut payload = Ga4MetricDisplayPayload::new(april_range());
        payload.cards.push(visitor_card());
        payload.validate().expect("valid payload");

        let value = serde_json::to_value(&payload).expect("payload json");

        assert_eq!(value["schema_version"], GA4_METRIC_DISPLAY_SCHEMA_VERSION);
        assert_eq!(value["provider"], GA4_METRIC_DISPLAY_PROVIDER);
        assert_eq!(value["date_range"]["label"], "April 2026");
        assert_eq!(value["date_range"]["start"], "2026-04-01");
        assert_eq!(value["date_range"]["end"], "2026-04-30");
    }

    #[test]
    fn metric_cards_serialize_into_safe_compact_display_objects() {
        let card = visitor_card();
        card.validate().expect("valid card");

        let value = serde_json::to_value(&card).expect("card json");

        assert_eq!(value["key"], "users");
        assert_eq!(value["label"], "Website Visitors");
        assert_eq!(value["value_kind"], "integer");
        assert_eq!(value["value"]["kind"], "integer");
        assert_eq!(value["value"]["value"], 1842);
        assert_eq!(value["formatted_value"], "1,842");
        assert_eq!(value["comparison"]["direction"], "up");
        assert_eq!(value["comparison"]["percent_change"], 7.1);
    }

    #[test]
    fn line_trend_serializes_with_safe_points() {
        let trend = users_trend();
        trend.validate().expect("valid trend");

        let value = serde_json::to_value(&trend).expect("trend json");

        assert_eq!(value["key"], "users_trend");
        assert_eq!(value["value_kind"], "integer");
        assert_eq!(value["points"][0]["date"], "2026-04-01");
        assert_eq!(value["points"][0]["value"], 54.0);
        assert_eq!(value["points"][1]["date"], "2026-04-02");
    }

    #[test]
    fn missing_comparison_data_is_omitted_cleanly() {
        let card = Ga4MetricCard::new(
            "sessions",
            "Visits",
            Ga4DisplayValue::Integer(2416),
            "2,416",
            Ga4DisplayAvailability::Available,
        )
        .expect("metric card");

        let value = serde_json::to_value(&card).expect("card json");

        assert!(value.get("comparison").is_none());
        assert_eq!(value["label"], "Visits");
    }

    #[test]
    fn empty_payload_uses_safe_empty_state() {
        let payload = Ga4MetricDisplayPayload::empty(
            april_range(),
            "Report data for this period is not available yet.",
        )
        .expect("empty payload");

        payload.validate().expect("valid empty payload");
        assert!(!payload.has_display_content());

        let value = serde_json::to_value(&payload).expect("payload json");
        assert_eq!(
            value["empty_state"]["message"],
            "Report data for this period is not available yet."
        );
        assert_eq!(value["empty_state"]["availability"], "missing");
    }

    #[test]
    fn compact_lists_support_safe_rows_and_metrics() {
        let row = Ga4CompactListRow::new(
            "Organic Search",
            vec![
                Ga4CompactMetric::new(
                    "sessions",
                    "Visits",
                    Ga4DisplayValue::Integer(1044),
                    "1,044",
                )
                .expect("sessions metric"),
                Ga4CompactMetric::new(
                    "key_events",
                    "Key Actions",
                    Ga4DisplayValue::Integer(31),
                    "31",
                )
                .expect("key events metric"),
            ],
        )
        .expect("row");
        let list = Ga4CompactList::new(
            "traffic_channels",
            "Top traffic channels",
            vec![row],
            Ga4DisplayAvailability::Available,
        )
        .expect("list");

        let value = serde_json::to_value(&list).expect("list json");

        assert_eq!(value["key"], "traffic_channels");
        assert_eq!(value["rows"][0]["label"], "Organic Search");
        assert_eq!(value["rows"][0]["metrics"][0]["value_kind"], "integer");
    }

    #[test]
    fn serialized_output_does_not_contain_forbidden_field_names() {
        let mut payload = Ga4MetricDisplayPayload::new(april_range());
        payload.cards.push(visitor_card());
        payload.trends.push(users_trend());
        payload.validate().expect("valid payload");

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

    #[test]
    fn value_kind_serialization_is_stable() {
        let kinds = serde_json::to_value([
            Ga4DisplayValueKind::Integer,
            Ga4DisplayValueKind::Decimal,
            Ga4DisplayValueKind::Percentage,
            Ga4DisplayValueKind::DurationSeconds,
            Ga4DisplayValueKind::Text,
        ])
        .expect("kinds json");

        assert_eq!(
            kinds,
            serde_json::json!([
                "integer",
                "decimal",
                "percentage",
                "duration_seconds",
                "text"
            ])
        );
    }

    #[test]
    fn date_ranges_reject_inverted_dates() {
        assert_eq!(
            Ga4MetricDisplayDateRange::new("Bad Period", date(2026, 4, 30), date(2026, 4, 1))
                .unwrap_err(),
            Ga4MetricDisplayValidationError::InvalidDateRange
        );
    }

    #[test]
    fn validation_rejects_unsafe_keys_and_labels() {
        assert_eq!(
            Ga4MetricCard::new(
                "source_snapshot_id",
                "Website Visitors",
                Ga4DisplayValue::Integer(10),
                "10",
                Ga4DisplayAvailability::Available,
            )
            .unwrap_err(),
            Ga4MetricDisplayValidationError::InvalidKey
        );
        assert_eq!(
            Ga4MetricCard::new(
                "users",
                "Provider metadata",
                Ga4DisplayValue::Integer(10),
                "10",
                Ga4DisplayAvailability::Available,
            )
            .unwrap_err(),
            Ga4MetricDisplayValidationError::InvalidDisplayText
        );
    }

    #[test]
    fn validation_rejects_non_finite_numbers() {
        assert_eq!(
            Ga4MetricCard::new(
                "engagement_rate",
                "Engagement Rate",
                Ga4DisplayValue::Percentage(f64::NAN),
                "Not available",
                Ga4DisplayAvailability::Malformed,
            )
            .unwrap_err(),
            Ga4MetricDisplayValidationError::InvalidNumber
        );
        assert_eq!(
            Ga4TrendPoint::new(date(2026, 4, 1), f64::INFINITY).unwrap_err(),
            Ga4MetricDisplayValidationError::InvalidNumber
        );
    }

    #[test]
    fn payload_without_content_or_empty_state_is_invalid() {
        let payload = Ga4MetricDisplayPayload::new(april_range());

        assert_eq!(
            payload.validate().unwrap_err(),
            Ga4MetricDisplayValidationError::MissingDisplayContent
        );
    }

    #[test]
    fn available_line_trend_requires_points() {
        assert_eq!(
            Ga4LineTrend::new(
                "users_trend",
                "Website visitors over time",
                Ga4DisplayValueKind::Integer,
                Vec::new(),
                Ga4DisplayAvailability::Available,
            )
            .unwrap_err(),
            Ga4MetricDisplayValidationError::MissingTrendPoints
        );
    }

    #[test]
    fn text_values_are_allowed_only_as_sanitized_display_values() {
        let value = Ga4DisplayValue::Text("Configured key action".to_string());
        value.validate().expect("safe text");

        let json: Value = serde_json::to_value(value).expect("text value json");
        assert_eq!(json["kind"], "text");
        assert_eq!(json["value"], "Configured key action");
    }
}
