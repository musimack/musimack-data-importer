use chrono::NaiveDate;
use serde_json::{Value, json};
use sqlx::{PgPool, Row};
use thiserror::Error;
use uuid::Uuid;

use crate::{
    ga4_metric_display::Ga4MetricDisplayPayload,
    ga4_metric_display_transform::{
        Ga4MetricDisplayTransformError, transform_ga4_snapshot_to_metric_display,
    },
    ga4_oauth::GA4_PROVIDER,
    ga4_snapshot::GA4_SNAPSHOT_SCHEMA_VERSION,
    ga4_snapshot_writer::GA4_SNAPSHOT_TYPE,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Ga4MetricDisplayReadScope {
    InternalDraft,
    PublishedClient,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Ga4MetricDisplayReadModel {
    pub project_id: Uuid,
    pub provider: String,
    pub snapshot_type: String,
    pub report_type: String,
    pub visibility: String,
    pub status: String,
    pub display: Ga4MetricDisplayPayload,
}

#[derive(Debug, Error)]
pub enum Ga4MetricDisplayReadError {
    #[error("GA4 metric display snapshot was not found")]
    NotFound,
    #[error("GA4 metric display snapshot belongs to a different project")]
    ProjectMismatch,
    #[error("GA4 metric display snapshot provider is unsupported")]
    UnsupportedProvider,
    #[error("GA4 metric display snapshot type is unsupported")]
    UnsupportedSnapshotType,
    #[error("GA4 metric display snapshot state is not allowed for this read scope")]
    UnsupportedSnapshotState,
    #[error("GA4 metric display snapshot schema is unsupported")]
    UnsupportedSchema,
    #[error("GA4 metric display snapshot payload is malformed")]
    MalformedSnapshot,
    #[error("GA4 metric display snapshot contains unsafe internal fields")]
    UnsafeSnapshot,
    #[error("GA4 metric display transform failed safely")]
    TransformFailed,
    #[error("database error while loading GA4 metric display")]
    Database(#[from] sqlx::Error),
}

impl PartialEq for Ga4MetricDisplayReadError {
    fn eq(&self, other: &Self) -> bool {
        std::mem::discriminant(self) == std::mem::discriminant(other)
    }
}

impl Eq for Ga4MetricDisplayReadError {}

pub async fn load_ga4_metric_display_for_snapshot(
    pool: &PgPool,
    project_id: Uuid,
    snapshot_id: Uuid,
    scope: Ga4MetricDisplayReadScope,
) -> Result<Ga4MetricDisplayReadModel, Ga4MetricDisplayReadError> {
    let row = sqlx::query(
        "select id, project_id, provider, snapshot_type, visibility, status, summary,
                metrics, dimensions, source_metadata, period_start, period_end
         from project_integration_snapshots
         where id = $1",
    )
    .bind(snapshot_id)
    .fetch_optional(pool)
    .await?
    .ok_or(Ga4MetricDisplayReadError::NotFound)?;

    let snapshot_project_id: Uuid = row.get("project_id");
    if snapshot_project_id != project_id {
        return Err(Ga4MetricDisplayReadError::ProjectMismatch);
    }

    let provider: String = row.get("provider");
    let snapshot_type: String = row.get("snapshot_type");
    if provider != GA4_PROVIDER {
        return Err(Ga4MetricDisplayReadError::UnsupportedProvider);
    }
    if snapshot_type != GA4_SNAPSHOT_TYPE {
        return Err(Ga4MetricDisplayReadError::UnsupportedSnapshotType);
    }

    let visibility: String = row.get("visibility");
    let status: String = row.get("status");
    validate_scope_state(scope, &visibility, &status)?;

    let metrics: Value = row.get("metrics");
    let dimensions: Value = row.get("dimensions");
    let source_metadata: Value = row.get("source_metadata");
    validate_safe_snapshot_value(&metrics)?;
    validate_safe_snapshot_value(&dimensions)?;
    validate_safe_snapshot_value(&source_metadata)?;

    let snapshot_payload =
        build_sanitized_snapshot_payload(&row, &metrics, &dimensions, &source_metadata)?;
    let display =
        transform_ga4_snapshot_to_metric_display(&snapshot_payload).map_err(map_transform_error)?;
    let report_type = source_metadata
        .get("report_type")
        .and_then(Value::as_str)
        .ok_or(Ga4MetricDisplayReadError::MalformedSnapshot)?
        .to_string();

    Ok(Ga4MetricDisplayReadModel {
        project_id,
        provider,
        snapshot_type,
        report_type,
        visibility,
        status,
        display,
    })
}

fn validate_scope_state(
    scope: Ga4MetricDisplayReadScope,
    visibility: &str,
    status: &str,
) -> Result<(), Ga4MetricDisplayReadError> {
    match scope {
        Ga4MetricDisplayReadScope::InternalDraft
            if visibility == "internal" && status == "draft" =>
        {
            Ok(())
        }
        Ga4MetricDisplayReadScope::PublishedClient
            if visibility == "client" && status == "published" =>
        {
            Ok(())
        }
        _ => Err(Ga4MetricDisplayReadError::UnsupportedSnapshotState),
    }
}

fn build_sanitized_snapshot_payload(
    row: &sqlx::postgres::PgRow,
    metrics: &Value,
    dimensions: &Value,
    source_metadata: &Value,
) -> Result<Value, Ga4MetricDisplayReadError> {
    let schema_version = source_metadata
        .get("schema_version")
        .and_then(Value::as_str)
        .ok_or(Ga4MetricDisplayReadError::UnsupportedSchema)?;
    if schema_version != GA4_SNAPSHOT_SCHEMA_VERSION {
        return Err(Ga4MetricDisplayReadError::UnsupportedSchema);
    }
    let report_type = source_metadata
        .get("report_type")
        .and_then(Value::as_str)
        .ok_or(Ga4MetricDisplayReadError::MalformedSnapshot)?;
    let property_resource = source_metadata
        .get("property_resource")
        .and_then(Value::as_str)
        .ok_or(Ga4MetricDisplayReadError::MalformedSnapshot)?;
    let date_range = display_date_range(row, dimensions)?;
    let comparison_date_range = dimensions
        .get("comparison_date_range")
        .and_then(normalize_date_range)
        .unwrap_or(Value::Null);
    let dimension_rows = dimensions
        .get("dimension_rows")
        .cloned()
        .unwrap_or_else(|| json!([]));

    let mut payload = json!({
        "schema_version": GA4_SNAPSHOT_SCHEMA_VERSION,
        "provider": "ga4",
        "provider_key": GA4_PROVIDER,
        "report_type": report_type,
        "property_resource": property_resource,
        "date_range": date_range,
        "comparison_date_range": comparison_date_range,
        "source": source_metadata.get("source").cloned().unwrap_or_else(|| json!("local_snapshot")),
        "summary": row.get::<String, _>("summary"),
        "metrics": metrics,
        "dimension_rows": dimension_rows,
        "summary_counts": source_metadata.get("summary_counts").cloned().unwrap_or_else(|| json!({})),
        "warnings": source_metadata.get("warnings").cloned().unwrap_or_else(|| json!([])),
    });

    if let Some(time_series) = dimensions.get("time_series") {
        payload["time_series"] = time_series.clone();
    }
    if let Some(previous_metrics) = dimensions.get("previous_metrics") {
        payload["previous_metrics"] = previous_metrics.clone();
    }

    Ok(payload)
}

fn display_date_range(
    row: &sqlx::postgres::PgRow,
    dimensions: &Value,
) -> Result<Value, Ga4MetricDisplayReadError> {
    if let Some(date_range) = dimensions.get("date_range").and_then(normalize_date_range) {
        return Ok(date_range);
    }

    let period_start: Option<NaiveDate> = row.get("period_start");
    let period_end: Option<NaiveDate> = row.get("period_end");
    let (Some(start), Some(end)) = (period_start, period_end) else {
        return Err(Ga4MetricDisplayReadError::MalformedSnapshot);
    };
    Ok(json!({
        "start": start.to_string(),
        "end": end.to_string(),
    }))
}

fn normalize_date_range(value: &Value) -> Option<Value> {
    let object = value.as_object()?;
    let start = object
        .get("start")
        .or_else(|| object.get("start_date"))
        .and_then(Value::as_str)?;
    let end = object
        .get("end")
        .or_else(|| object.get("end_date"))
        .and_then(Value::as_str)?;
    Some(json!({
        "start": start,
        "end": end,
    }))
}

fn map_transform_error(error: Ga4MetricDisplayTransformError) -> Ga4MetricDisplayReadError {
    match error {
        Ga4MetricDisplayTransformError::InvalidSchemaVersion => {
            Ga4MetricDisplayReadError::UnsupportedSchema
        }
        Ga4MetricDisplayTransformError::InvalidProvider
        | Ga4MetricDisplayTransformError::UnsupportedReportType => {
            Ga4MetricDisplayReadError::UnsupportedProvider
        }
        Ga4MetricDisplayTransformError::UnsafePayload => Ga4MetricDisplayReadError::UnsafeSnapshot,
        _ => Ga4MetricDisplayReadError::TransformFailed,
    }
}

fn validate_safe_snapshot_value(value: &Value) -> Result<(), Ga4MetricDisplayReadError> {
    match value {
        Value::Object(object) => {
            for (key, nested) in object {
                if contains_forbidden_term(key) {
                    return Err(Ga4MetricDisplayReadError::UnsafeSnapshot);
                }
                validate_safe_snapshot_value(nested)?;
            }
        }
        Value::Array(values) => {
            for nested in values {
                validate_safe_snapshot_value(nested)?;
            }
        }
        Value::String(text) if contains_forbidden_term(text) => {
            return Err(Ga4MetricDisplayReadError::UnsafeSnapshot);
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
    "raw_provider",
    "google_response",
    "stack_trace",
];

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ga4_metric_display::Ga4DisplayAvailability;
    use sqlx::postgres::PgPoolOptions;

    #[tokio::test]
    async fn valid_local_ga4_snapshot_produces_metric_cards_and_trends()
    -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "internal",
            "draft",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let model = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await?;

        assert_eq!(model.project_id, fixture.project_id);
        assert_eq!(model.report_type, "traffic_overview");
        assert_eq!(model.display.schema_version, "ga4_metric_display.v1");
        assert!(model.display.cards.iter().any(|card| card.key == "users"));
        assert!(
            model
                .display
                .cards
                .iter()
                .any(|card| card.key == "sessions")
        );
        assert!(model.display.trends.iter().any(|trend| {
            trend.key == "users_trend" && trend.availability == Ga4DisplayAvailability::Available
        }));
        assert!(model.display.trends.iter().any(|trend| {
            trend.key == "sessions_trend" && trend.availability == Ga4DisplayAvailability::Available
        }));
        let users = model
            .display
            .cards
            .iter()
            .find(|card| card.key == "users")
            .expect("users card");
        assert!(users.comparison.is_some());

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn missing_time_series_produces_safe_missing_trend()
    -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "internal",
            "draft",
            ga4_metrics(),
            ga4_dimensions_without_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let model = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await?;

        assert_eq!(model.display.trends.len(), 1);
        assert_eq!(model.display.trends[0].key, "users_trend");
        assert!(model.display.trends[0].points.is_empty());

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn non_ga4_snapshot_is_rejected_safely() -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_snapshot(
            &pool,
            fixture.project_id,
            fixture.integration_account_id,
            "monday",
            "monday_tasks",
            "internal",
            "draft",
            json!({"open_items": 3}),
            json!({}),
            json!({"schema_version": "monday_snapshot.v1"}),
        )
        .await?;

        let error = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await
        .unwrap_err();
        assert_eq!(error, Ga4MetricDisplayReadError::UnsupportedProvider);

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn unsupported_snapshot_type_is_rejected_safely() -> Result<(), Box<dyn std::error::Error>>
    {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_snapshot(
            &pool,
            fixture.project_id,
            fixture.integration_account_id,
            GA4_PROVIDER,
            "custom",
            "internal",
            "draft",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let error = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await
        .unwrap_err();
        assert_eq!(error, Ga4MetricDisplayReadError::UnsupportedSnapshotType);

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn unsupported_schema_is_rejected_safely() -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "internal",
            "draft",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", "ga4_snapshot.v0"),
        )
        .await?;

        let error = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await
        .unwrap_err();
        assert_eq!(error, Ga4MetricDisplayReadError::UnsupportedSchema);

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn snapshot_project_mismatch_is_rejected() -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let other_fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "internal",
            "draft",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let error = load_ga4_metric_display_for_snapshot(
            &pool,
            other_fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await
        .unwrap_err();
        assert_eq!(error, Ga4MetricDisplayReadError::ProjectMismatch);

        cleanup_fixture(&pool, &fixture).await?;
        cleanup_fixture(&pool, &other_fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn malformed_snapshot_payload_does_not_panic() -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "internal",
            "draft",
            json!([{"name": "users", "value": "many", "unit": "count"}]),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let error = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await
        .unwrap_err();
        assert_eq!(error, Ga4MetricDisplayReadError::TransformFailed);

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn unsafe_snapshot_payload_is_rejected_without_leaky_error()
    -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "internal",
            "draft",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            json!({
                "schema_version": GA4_SNAPSHOT_SCHEMA_VERSION,
                "provider_key": GA4_PROVIDER,
                "source": "stub",
                "report_type": "traffic_overview",
                "property_resource": "properties/123456789",
                "access_token": "not allowed"
            }),
        )
        .await?;

        let error = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await
        .unwrap_err();
        let message = error.to_string();
        assert_eq!(error, Ga4MetricDisplayReadError::UnsafeSnapshot);
        assert!(!message.contains("access_token"));
        assert!(!message.contains("not allowed"));

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn published_client_scope_accepts_published_client_snapshots()
    -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "client",
            "published",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let model = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::PublishedClient,
        )
        .await?;

        assert_eq!(model.visibility, "client");
        assert_eq!(model.status, "published");

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn wrong_snapshot_state_is_rejected_for_scope() -> Result<(), Box<dyn std::error::Error>>
    {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "client",
            "published",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let error = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await
        .unwrap_err();
        assert_eq!(error, Ga4MetricDisplayReadError::UnsupportedSnapshotState);

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn serialized_display_output_contains_no_forbidden_fields()
    -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let snapshot_id = insert_ga4_snapshot(
            &pool,
            &fixture,
            "internal",
            "draft",
            ga4_metrics(),
            ga4_dimensions_with_time_series(),
            ga4_source_metadata("traffic_overview", GA4_SNAPSHOT_SCHEMA_VERSION),
        )
        .await?;

        let model = load_ga4_metric_display_for_snapshot(
            &pool,
            fixture.project_id,
            snapshot_id,
            Ga4MetricDisplayReadScope::InternalDraft,
        )
        .await?;
        let text = serde_json::to_string(&model.display).expect("display json");

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
                "forbidden field leaked into metric display read model: {forbidden}"
            );
        }

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    async fn optional_pool() -> Result<Option<PgPool>, sqlx::Error> {
        let Ok(database_url) = std::env::var("DATABASE_URL") else {
            return Ok(None);
        };
        let pool = PgPoolOptions::new()
            .max_connections(2)
            .connect(&database_url)
            .await?;
        sqlx::migrate!("./migrations").run(&pool).await?;
        Ok(Some(pool))
    }

    struct Fixture {
        client_id: Uuid,
        project_id: Uuid,
        integration_account_id: Uuid,
    }

    async fn seed_fixture(pool: &PgPool) -> Result<Fixture, sqlx::Error> {
        let suffix = Uuid::new_v4();
        let client_id: Uuid =
            sqlx::query_scalar("insert into clients (name) values ($1) returning id")
                .bind(format!("GA4 Metric Display Reader Client {suffix}"))
                .fetch_one(pool)
                .await?;
        let project_id: Uuid = sqlx::query_scalar(
            "insert into projects (client_id, name, root_domain, allowed_hosts, verification_status)
             values ($1, $2, $3, $4, 'verified') returning id",
        )
        .bind(client_id)
        .bind(format!("GA4 Metric Display Reader Project {suffix}"))
        .bind(format!("ga4-display-reader-{suffix}.example"))
        .bind(Vec::<String>::new())
        .fetch_one(pool)
        .await?;
        let integration_account_id: Uuid = sqlx::query_scalar(
            "insert into integration_accounts
                (provider, account_name, external_account_id, connection_status, metadata)
             values ('google_analytics', $1, $2, 'planned', $3) returning id",
        )
        .bind(format!("GA4 Metric Display Reader Account {suffix}"))
        .bind(format!("ga4-display-reader-account-{suffix}"))
        .bind(json!({"fixture": true, "live_sync": false}))
        .fetch_one(pool)
        .await?;

        Ok(Fixture {
            client_id,
            project_id,
            integration_account_id,
        })
    }

    async fn cleanup_fixture(pool: &PgPool, fixture: &Fixture) -> Result<(), sqlx::Error> {
        sqlx::query("delete from integration_accounts where id = $1")
            .bind(fixture.integration_account_id)
            .execute(pool)
            .await?;
        sqlx::query("delete from clients where id = $1")
            .bind(fixture.client_id)
            .execute(pool)
            .await?;
        Ok(())
    }

    async fn insert_ga4_snapshot(
        pool: &PgPool,
        fixture: &Fixture,
        visibility: &str,
        status: &str,
        metrics: Value,
        dimensions: Value,
        source_metadata: Value,
    ) -> Result<Uuid, sqlx::Error> {
        insert_snapshot(
            pool,
            fixture.project_id,
            fixture.integration_account_id,
            GA4_PROVIDER,
            GA4_SNAPSHOT_TYPE,
            visibility,
            status,
            metrics,
            dimensions,
            source_metadata,
        )
        .await
    }

    async fn insert_snapshot(
        pool: &PgPool,
        project_id: Uuid,
        integration_account_id: Uuid,
        provider: &str,
        snapshot_type: &str,
        visibility: &str,
        status: &str,
        metrics: Value,
        dimensions: Value,
        source_metadata: Value,
    ) -> Result<Uuid, sqlx::Error> {
        sqlx::query_scalar(
            "insert into project_integration_snapshots
                (project_id, integration_account_id, provider, snapshot_type,
                 period_start, period_end, visibility, status, summary,
                 metrics, dimensions, source_metadata)
             values ($1, $2, $3, $4, '2026-04-01', '2026-04-30', $5, $6,
                     'Safe GA4 metric display reader fixture.', $7, $8, $9)
             returning id",
        )
        .bind(project_id)
        .bind(integration_account_id)
        .bind(provider)
        .bind(snapshot_type)
        .bind(visibility)
        .bind(status)
        .bind(metrics)
        .bind(dimensions)
        .bind(source_metadata)
        .fetch_one(pool)
        .await
    }

    fn ga4_metrics() -> Value {
        json!([
            {"name": "users", "value": 1842.0, "unit": "count"},
            {"name": "new_users", "value": 1110.0, "unit": "count"},
            {"name": "sessions", "value": 2416.0, "unit": "count"},
            {"name": "engaged_sessions", "value": 1490.0, "unit": "count"},
            {"name": "engagement_rate", "value": 0.617, "unit": "ratio"},
            {"name": "average_engagement_time_seconds", "value": 83.0, "unit": "seconds"},
            {"name": "key_events", "value": 74.0, "unit": "count"}
        ])
    }

    fn ga4_dimensions_with_time_series() -> Value {
        json!({
            "date_range": {"period_label": "April 2026", "start_date": "2026-04-01", "end_date": "2026-04-30"},
            "comparison_date_range": {"start_date": "2026-03-01", "end_date": "2026-03-31"},
            "previous_metrics": [
                {"name": "users", "value": 1700.0, "unit": "count"},
                {"name": "new_users", "value": 1000.0, "unit": "count"},
                {"name": "sessions", "value": 2200.0, "unit": "count"},
                {"name": "engaged_sessions", "value": 1400.0, "unit": "count"},
                {"name": "engagement_rate", "value": 0.60, "unit": "ratio"},
                {"name": "average_engagement_time_seconds", "value": 70.0, "unit": "seconds"},
                {"name": "key_events", "value": 60.0, "unit": "count"}
            ],
            "dimension_rows": [],
            "time_series": [
                {"date": "2026-04-01", "users": 54.0, "sessions": 72.0},
                {"date": "2026-04-02", "users": 61.0, "sessions": 80.0},
                {"date": "2026-04-03", "users": 58.0, "sessions": 76.0}
            ]
        })
    }

    fn ga4_dimensions_without_time_series() -> Value {
        json!({
            "date_range": {"start": "2026-04-01", "end": "2026-04-30"},
            "comparison_date_range": null,
            "dimension_rows": []
        })
    }

    fn ga4_source_metadata(report_type: &str, schema_version: &str) -> Value {
        json!({
            "schema_version": schema_version,
            "provider_key": GA4_PROVIDER,
            "source": "stub",
            "report_type": report_type,
            "property_resource": "properties/123456789",
            "summary_counts": {
                "metric_count": 7,
                "dimension_row_count": 0
            },
            "warnings": []
        })
    }
}
