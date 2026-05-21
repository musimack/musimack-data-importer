use chrono::NaiveDate;
use thiserror::Error;
use uuid::Uuid;

use crate::ga4_oauth::GA4_PROVIDER;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Ga4ReportType {
    TrafficOverview,
    ChannelBreakdown,
    TopPages,
    ConversionsSummary,
}

impl Ga4ReportType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::TrafficOverview => "traffic_overview",
            Self::ChannelBreakdown => "channel_breakdown",
            Self::TopPages => "top_pages",
            Self::ConversionsSummary => "conversions_summary",
        }
    }

    pub fn parse(value: &str) -> Result<Self, Ga4ReportingError> {
        match value.trim() {
            "traffic_overview" => Ok(Self::TrafficOverview),
            "channel_breakdown" => Ok(Self::ChannelBreakdown),
            "top_pages" => Ok(Self::TopPages),
            "conversions_summary" => Ok(Self::ConversionsSummary),
            _ => Err(Ga4ReportingError::UnsupportedReportType),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Ga4ReportingDateRange {
    start: NaiveDate,
    end: NaiveDate,
}

impl Ga4ReportingDateRange {
    pub fn new(start: NaiveDate, end: NaiveDate) -> Result<Self, Ga4ReportingError> {
        if end < start {
            return Err(Ga4ReportingError::InvalidDateRange);
        }
        Ok(Self { start, end })
    }

    pub fn start(&self) -> NaiveDate {
        self.start
    }

    pub fn end(&self) -> NaiveDate {
        self.end
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ga4ReportingQueryRequest {
    project_id: Option<Uuid>,
    property_resource_id: String,
    date_range: Ga4ReportingDateRange,
    comparison_date_range: Option<Ga4ReportingDateRange>,
    report_type: Ga4ReportType,
}

impl Ga4ReportingQueryRequest {
    pub fn new(
        project_id: Option<Uuid>,
        property_resource_id: impl Into<String>,
        date_range: Ga4ReportingDateRange,
        comparison_date_range: Option<Ga4ReportingDateRange>,
        report_type: Ga4ReportType,
    ) -> Result<Self, Ga4ReportingError> {
        let property_resource_id = property_resource_id.into();
        validate_property_resource_id(&property_resource_id)?;

        Ok(Self {
            project_id,
            property_resource_id,
            date_range,
            comparison_date_range,
            report_type,
        })
    }

    pub fn project_id(&self) -> Option<Uuid> {
        self.project_id
    }

    pub fn property_resource_id(&self) -> &str {
        &self.property_resource_id
    }

    pub fn date_range(&self) -> Ga4ReportingDateRange {
        self.date_range
    }

    pub fn comparison_date_range(&self) -> Option<Ga4ReportingDateRange> {
        self.comparison_date_range
    }

    pub fn report_type(&self) -> Ga4ReportType {
        self.report_type
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Ga4ReportingMetric {
    pub name: String,
    pub value: f64,
    pub unit: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Ga4ReportingDimensionRow {
    pub label: String,
    pub metrics: Vec<Ga4ReportingMetric>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Ga4ReportingResult {
    pub provider: String,
    pub property_resource_id: String,
    pub report_type: Ga4ReportType,
    pub date_range: Ga4ReportingDateRange,
    pub metrics: Vec<Ga4ReportingMetric>,
    pub rows: Vec<Ga4ReportingDimensionRow>,
    pub summary: String,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum Ga4ReportingError {
    #[error("live GA4 reporting queries are not implemented")]
    LiveReportingDisabled,
    #[error("GA4 reporting date range is invalid")]
    InvalidDateRange,
    #[error("GA4 property resource id is required and must use properties/{{id}} format")]
    InvalidPropertyResource,
    #[error("GA4 report type is not supported")]
    UnsupportedReportType,
}

pub trait Ga4ReportingQueryClient {
    fn run_report(
        &self,
        request: &Ga4ReportingQueryRequest,
    ) -> Result<Ga4ReportingResult, Ga4ReportingError>;
}

pub struct DisabledGa4ReportingQueryClient;

impl Ga4ReportingQueryClient for DisabledGa4ReportingQueryClient {
    fn run_report(
        &self,
        _request: &Ga4ReportingQueryRequest,
    ) -> Result<Ga4ReportingResult, Ga4ReportingError> {
        Err(Ga4ReportingError::LiveReportingDisabled)
    }
}

#[derive(Debug, Default)]
pub struct StubGa4ReportingQueryClient;

impl Ga4ReportingQueryClient for StubGa4ReportingQueryClient {
    fn run_report(
        &self,
        request: &Ga4ReportingQueryRequest,
    ) -> Result<Ga4ReportingResult, Ga4ReportingError> {
        Ok(match request.report_type() {
            Ga4ReportType::TrafficOverview => stub_traffic_overview(request),
            Ga4ReportType::ChannelBreakdown => stub_channel_breakdown(request),
            Ga4ReportType::TopPages => stub_top_pages(request),
            Ga4ReportType::ConversionsSummary => stub_conversions_summary(request),
        })
    }
}

fn validate_property_resource_id(value: &str) -> Result<(), Ga4ReportingError> {
    let Some(id) = value.trim().strip_prefix("properties/") else {
        return Err(Ga4ReportingError::InvalidPropertyResource);
    };
    if id.trim().is_empty() || !id.chars().all(|character| character.is_ascii_digit()) {
        return Err(Ga4ReportingError::InvalidPropertyResource);
    }
    Ok(())
}

fn stub_traffic_overview(request: &Ga4ReportingQueryRequest) -> Ga4ReportingResult {
    result(
        request,
        vec![
            metric("users", 1240.0, "count"),
            metric("sessions", 1688.0, "count"),
            metric("engaged_sessions", 1042.0, "count"),
            metric("engagement_rate", 0.617, "ratio"),
            metric("views", 3925.0, "count"),
        ],
        vec![],
        "Fake GA4 traffic overview for local boundary testing only.",
    )
}

fn stub_channel_breakdown(request: &Ga4ReportingQueryRequest) -> Ga4ReportingResult {
    result(
        request,
        vec![metric("sessions", 1688.0, "count")],
        vec![
            row("Organic Search", vec![metric("sessions", 724.0, "count")]),
            row("Direct", vec![metric("sessions", 438.0, "count")]),
            row("Referral", vec![metric("sessions", 291.0, "count")]),
            row("Paid Search", vec![metric("sessions", 235.0, "count")]),
        ],
        "Fake GA4 channel breakdown for local boundary testing only.",
    )
}

fn stub_top_pages(request: &Ga4ReportingQueryRequest) -> Ga4ReportingResult {
    result(
        request,
        vec![metric("views", 3925.0, "count")],
        vec![
            row("/services", vec![metric("views", 812.0, "count")]),
            row("/contact", vec![metric("views", 529.0, "count")]),
            row("/case-studies", vec![metric("views", 388.0, "count")]),
        ],
        "Fake GA4 top pages report for local boundary testing only.",
    )
}

fn stub_conversions_summary(request: &Ga4ReportingQueryRequest) -> Ga4ReportingResult {
    result(
        request,
        vec![
            metric("conversions", 42.0, "count"),
            metric("key_events", 57.0, "count"),
            metric("event_count", 684.0, "count"),
        ],
        vec![],
        "Fake GA4 conversions summary for local boundary testing only.",
    )
}

fn result(
    request: &Ga4ReportingQueryRequest,
    metrics: Vec<Ga4ReportingMetric>,
    rows: Vec<Ga4ReportingDimensionRow>,
    summary: &str,
) -> Ga4ReportingResult {
    Ga4ReportingResult {
        provider: GA4_PROVIDER.to_string(),
        property_resource_id: request.property_resource_id().to_string(),
        report_type: request.report_type(),
        date_range: request.date_range(),
        metrics,
        rows,
        summary: summary.to_string(),
    }
}

fn metric(name: &str, value: f64, unit: &str) -> Ga4ReportingMetric {
    Ga4ReportingMetric {
        name: name.to_string(),
        value,
        unit: unit.to_string(),
    }
}

fn row(label: &str, metrics: Vec<Ga4ReportingMetric>) -> Ga4ReportingDimensionRow {
    Ga4ReportingDimensionRow {
        label: label.to_string(),
        metrics,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn date(year: i32, month: u32, day: u32) -> NaiveDate {
        NaiveDate::from_ymd_opt(year, month, day).expect("test date")
    }

    fn range() -> Ga4ReportingDateRange {
        Ga4ReportingDateRange::new(date(2026, 4, 1), date(2026, 4, 30)).expect("date range")
    }

    fn request(report_type: Ga4ReportType) -> Ga4ReportingQueryRequest {
        Ga4ReportingQueryRequest::new(
            Some(Uuid::nil()),
            "properties/123456789",
            range(),
            None,
            report_type,
        )
        .expect("query request")
    }

    #[test]
    fn live_reporting_client_is_disabled_by_default() {
        let client = DisabledGa4ReportingQueryClient;
        let error = client
            .run_report(&request(Ga4ReportType::TrafficOverview))
            .unwrap_err();

        assert_eq!(error, Ga4ReportingError::LiveReportingDisabled);
    }

    #[test]
    fn stub_reporting_client_returns_fake_traffic_overview_data() {
        let client = StubGa4ReportingQueryClient;
        let result = client
            .run_report(&request(Ga4ReportType::TrafficOverview))
            .expect("stub result");

        assert_eq!(result.provider, GA4_PROVIDER);
        assert_eq!(result.property_resource_id, "properties/123456789");
        assert_eq!(result.report_type, Ga4ReportType::TrafficOverview);
        assert!(result.summary.contains("Fake GA4"));
        assert!(result.metrics.iter().any(|metric| metric.name == "users"));
        assert!(result.rows.is_empty());
    }

    #[test]
    fn stub_reporting_client_returns_fake_channel_and_top_page_data() {
        let client = StubGa4ReportingQueryClient;
        let channels = client
            .run_report(&request(Ga4ReportType::ChannelBreakdown))
            .expect("channel result");
        let top_pages = client
            .run_report(&request(Ga4ReportType::TopPages))
            .expect("top pages result");

        assert_eq!(channels.rows[0].label, "Organic Search");
        assert_eq!(top_pages.rows[0].label, "/services");
    }

    #[test]
    fn invalid_date_ranges_are_rejected_safely() {
        assert_eq!(
            Ga4ReportingDateRange::new(date(2026, 5, 1), date(2026, 4, 30)).unwrap_err(),
            Ga4ReportingError::InvalidDateRange
        );
    }

    #[test]
    fn unsupported_report_types_are_rejected_safely() {
        assert_eq!(
            Ga4ReportType::parse("raw_provider_dump").unwrap_err(),
            Ga4ReportingError::UnsupportedReportType
        );
    }

    #[test]
    fn missing_or_invalid_property_resources_are_rejected_safely() {
        for value in ["", "properties/", "properties/not-real", "accounts/123"] {
            assert_eq!(
                Ga4ReportingQueryRequest::new(
                    None,
                    value,
                    range(),
                    None,
                    Ga4ReportType::TrafficOverview,
                )
                .unwrap_err(),
                Ga4ReportingError::InvalidPropertyResource
            );
        }
    }

    #[test]
    fn reporting_boundary_does_not_require_credentials_or_refresh() {
        let client = StubGa4ReportingQueryClient;
        let request = Ga4ReportingQueryRequest::new(
            None,
            "properties/123456789",
            range(),
            None,
            Ga4ReportType::ConversionsSummary,
        )
        .expect("request without project or credentials");

        let result = client.run_report(&request).expect("stub result");

        assert_eq!(result.report_type, Ga4ReportType::ConversionsSummary);
        assert!(
            result
                .metrics
                .iter()
                .any(|metric| metric.name == "conversions")
        );
    }

    #[test]
    fn debug_output_and_results_do_not_include_secret_field_names() {
        let client = StubGa4ReportingQueryClient;
        let result = client
            .run_report(&request(Ga4ReportType::TrafficOverview))
            .expect("stub result");
        let debug = format!("{result:?}");
        let error = Ga4ReportType::parse("refresh_token")
            .unwrap_err()
            .to_string();

        for forbidden in [
            "access_token",
            "refresh_token",
            "id_token",
            "api_key",
            "credentials_ref",
            "encrypted_payload",
            "client_secret",
        ] {
            assert!(!debug.contains(forbidden));
            assert!(!error.contains(forbidden));
        }
    }
}
