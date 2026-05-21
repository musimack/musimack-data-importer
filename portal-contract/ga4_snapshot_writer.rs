use chrono::{DateTime, NaiveDate, Utc};
use serde_json::{Value, json};
use sqlx::{Postgres, Row, Transaction};
use thiserror::Error;
use uuid::Uuid;

use crate::{
    ga4_oauth::GA4_PROVIDER, ga4_reporting::Ga4ReportType,
    ga4_snapshot::GA4_SNAPSHOT_SCHEMA_VERSION,
};

pub const GA4_SNAPSHOT_TYPE: &str = "ga4_summary";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapshotVisibility {
    Internal,
    Client,
}

impl SnapshotVisibility {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Internal => "internal",
            Self::Client => "client",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapshotStatus {
    Draft,
    Published,
    Archived,
}

impl SnapshotStatus {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Draft => "draft",
            Self::Published => "published",
            Self::Archived => "archived",
        }
    }
}

#[derive(Debug, Clone)]
pub struct Ga4SnapshotInsertRequest {
    project_id: Option<Uuid>,
    integration_account_id: Option<Uuid>,
    sync_run_id: Option<Uuid>,
    visibility: SnapshotVisibility,
    status: SnapshotStatus,
    payload: Value,
}

impl Ga4SnapshotInsertRequest {
    pub fn new(
        project_id: Option<Uuid>,
        integration_account_id: Option<Uuid>,
        sync_run_id: Option<Uuid>,
        visibility: SnapshotVisibility,
        status: SnapshotStatus,
        payload: Value,
    ) -> Self {
        Self {
            project_id,
            integration_account_id,
            sync_run_id,
            visibility,
            status,
            payload,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ga4SnapshotWriteOutcome {
    pub snapshot_id: Uuid,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Error)]
pub enum Ga4SnapshotWriteError {
    #[error("project_id is required for GA4 snapshot writes")]
    MissingProjectContext,
    #[error("integration_account_id is required for GA4 snapshot writes")]
    MissingIntegrationAccountContext,
    #[error("GA4 snapshot payload must be a JSON object")]
    InvalidPayload,
    #[error("GA4 snapshot payload schema version is unsupported")]
    InvalidSchemaVersion,
    #[error("GA4 snapshot payload provider is unsupported")]
    InvalidProvider,
    #[error("GA4 snapshot payload report type is unsupported")]
    UnsupportedReportType,
    #[error("GA4 snapshot payload property resource is invalid")]
    InvalidPropertyResource,
    #[error("GA4 snapshot payload date range is invalid")]
    InvalidDateRange,
    #[error("GA4 snapshot payload summary is required")]
    MissingSummary,
    #[error("GA4 snapshot payload contains unsafe secret-like fields")]
    UnsafePayload,
    #[error("database error while writing GA4 snapshot")]
    Database(#[from] sqlx::Error),
}

pub async fn insert_ga4_snapshot_payload(
    transaction: &mut Transaction<'_, Postgres>,
    request: &Ga4SnapshotInsertRequest,
) -> Result<Ga4SnapshotWriteOutcome, Ga4SnapshotWriteError> {
    let insert = build_ga4_snapshot_insert(request)?;

    let row = sqlx::query(
        "insert into project_integration_snapshots
            (project_id, integration_account_id, sync_run_id, provider, snapshot_type,
             period_start, period_end, visibility, status, summary, metrics, dimensions,
             source_metadata)
         values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
         returning id, created_at",
    )
    .bind(insert.project_id)
    .bind(insert.integration_account_id)
    .bind(insert.sync_run_id)
    .bind(GA4_PROVIDER)
    .bind(GA4_SNAPSHOT_TYPE)
    .bind(insert.period_start)
    .bind(insert.period_end)
    .bind(insert.visibility.as_str())
    .bind(insert.status.as_str())
    .bind(&insert.summary)
    .bind(&insert.metrics)
    .bind(&insert.dimensions)
    .bind(&insert.source_metadata)
    .fetch_one(&mut **transaction)
    .await?;

    Ok(Ga4SnapshotWriteOutcome {
        snapshot_id: row.get("id"),
        created_at: row.get("created_at"),
    })
}

#[derive(Debug, Clone)]
struct Ga4SnapshotInsert {
    project_id: Uuid,
    integration_account_id: Uuid,
    sync_run_id: Option<Uuid>,
    period_start: NaiveDate,
    period_end: NaiveDate,
    visibility: SnapshotVisibility,
    status: SnapshotStatus,
    summary: String,
    metrics: Value,
    dimensions: Value,
    source_metadata: Value,
}

fn build_ga4_snapshot_insert(
    request: &Ga4SnapshotInsertRequest,
) -> Result<Ga4SnapshotInsert, Ga4SnapshotWriteError> {
    let project_id = request
        .project_id
        .filter(|id| !id.is_nil())
        .ok_or(Ga4SnapshotWriteError::MissingProjectContext)?;
    let integration_account_id = request
        .integration_account_id
        .filter(|id| !id.is_nil())
        .ok_or(Ga4SnapshotWriteError::MissingIntegrationAccountContext)?;
    validate_no_secret_like_fields(&request.payload)?;

    let payload = request
        .payload
        .as_object()
        .ok_or(Ga4SnapshotWriteError::InvalidPayload)?;
    expect_str(payload.get("schema_version"))
        .filter(|value| *value == GA4_SNAPSHOT_SCHEMA_VERSION)
        .ok_or(Ga4SnapshotWriteError::InvalidSchemaVersion)?;
    expect_str(payload.get("provider"))
        .filter(|value| *value == "ga4")
        .ok_or(Ga4SnapshotWriteError::InvalidProvider)?;
    expect_str(payload.get("provider_key"))
        .filter(|value| *value == GA4_PROVIDER)
        .ok_or(Ga4SnapshotWriteError::InvalidProvider)?;

    let report_type = expect_str(payload.get("report_type"))
        .ok_or(Ga4SnapshotWriteError::UnsupportedReportType)?;
    Ga4ReportType::parse(report_type).map_err(|_| Ga4SnapshotWriteError::UnsupportedReportType)?;

    let property_resource = expect_str(payload.get("property_resource"))
        .ok_or(Ga4SnapshotWriteError::InvalidPropertyResource)?;
    validate_property_resource(property_resource)?;

    let date_range = payload
        .get("date_range")
        .and_then(Value::as_object)
        .ok_or(Ga4SnapshotWriteError::InvalidDateRange)?;
    let period_start = parse_date(date_range.get("start"))?;
    let period_end = parse_date(date_range.get("end"))?;
    if period_end < period_start {
        return Err(Ga4SnapshotWriteError::InvalidDateRange);
    }

    let summary = expect_str(payload.get("summary"))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or(Ga4SnapshotWriteError::MissingSummary)?
        .to_string();
    let metrics = payload
        .get("metrics")
        .filter(|value| value.is_array())
        .cloned()
        .ok_or(Ga4SnapshotWriteError::InvalidPayload)?;
    let dimensions = json!({
        "date_range": payload.get("date_range").cloned().unwrap_or(Value::Null),
        "comparison_date_range": payload.get("comparison_date_range").cloned().unwrap_or(Value::Null),
        "dimension_rows": payload.get("dimension_rows").cloned().unwrap_or_else(|| json!([])),
    });
    let source_value = payload.get("source").cloned().unwrap_or(Value::Null);
    let live_sync = source_value.as_str() == Some("future_live");
    let source_metadata = json!({
        "schema_version": GA4_SNAPSHOT_SCHEMA_VERSION,
        "provider_key": GA4_PROVIDER,
        "source": source_value,
        "report_type": report_type,
        "property_resource": property_resource,
        "summary_counts": payload.get("summary_counts").cloned().unwrap_or_else(|| json!({})),
        "warnings": payload.get("warnings").cloned().unwrap_or_else(|| json!([])),
        "snapshot_writer": "ga4_snapshot_writer",
        "live_sync": live_sync,
    });

    Ok(Ga4SnapshotInsert {
        project_id,
        integration_account_id,
        sync_run_id: request.sync_run_id,
        period_start,
        period_end,
        visibility: request.visibility,
        status: request.status,
        summary,
        metrics,
        dimensions,
        source_metadata,
    })
}

fn expect_str(value: Option<&Value>) -> Option<&str> {
    value.and_then(Value::as_str).map(str::trim)
}

fn parse_date(value: Option<&Value>) -> Result<NaiveDate, Ga4SnapshotWriteError> {
    NaiveDate::parse_from_str(
        expect_str(value).ok_or(Ga4SnapshotWriteError::InvalidDateRange)?,
        "%Y-%m-%d",
    )
    .map_err(|_| Ga4SnapshotWriteError::InvalidDateRange)
}

fn validate_property_resource(value: &str) -> Result<(), Ga4SnapshotWriteError> {
    let Some(id) = value.strip_prefix("properties/") else {
        return Err(Ga4SnapshotWriteError::InvalidPropertyResource);
    };
    if id.is_empty() || !id.chars().all(|character| character.is_ascii_digit()) {
        return Err(Ga4SnapshotWriteError::InvalidPropertyResource);
    }
    Ok(())
}

fn validate_no_secret_like_fields(value: &Value) -> Result<(), Ga4SnapshotWriteError> {
    let text = value.to_string();
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
        if text.contains(forbidden) {
            return Err(Ga4SnapshotWriteError::UnsafePayload);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::{PgPool, postgres::PgPoolOptions};

    use crate::ga4_reporting::{
        Ga4ReportType, Ga4ReportingQueryClient, Ga4ReportingQueryRequest,
        StubGa4ReportingQueryClient,
    };
    use crate::ga4_snapshot::{
        Ga4SnapshotSource, transform_ga4_reporting_result_to_snapshot_payload,
    };

    #[tokio::test]
    async fn valid_ga4_snapshot_payload_inserts_inside_transaction()
    -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let payload = snapshot_payload(Ga4ReportType::TrafficOverview)?;
        let request = request(&fixture, payload);

        let mut transaction = pool.begin().await?;
        let outcome = insert_ga4_snapshot_payload(&mut transaction, &request).await?;
        transaction.commit().await?;

        let row = sqlx::query(
            "select provider, snapshot_type, period_start, period_end, visibility, status,
                    summary, metrics, dimensions, source_metadata
             from project_integration_snapshots
             where id = $1",
        )
        .bind(outcome.snapshot_id)
        .fetch_one(&pool)
        .await?;
        let provider: String = row.get("provider");
        let snapshot_type: String = row.get("snapshot_type");
        let metrics: Value = row.get("metrics");
        let dimensions: Value = row.get("dimensions");
        let source_metadata: Value = row.get("source_metadata");

        assert_eq!(provider, GA4_PROVIDER);
        assert_eq!(snapshot_type, GA4_SNAPSHOT_TYPE);
        assert_eq!(metrics[0]["name"], "users");
        assert_eq!(dimensions["date_range"]["start"], "2026-04-01");
        assert_eq!(
            source_metadata["schema_version"],
            GA4_SNAPSHOT_SCHEMA_VERSION
        );
        assert_eq!(source_metadata["live_sync"], false);
        assert_no_secret_text(&metrics);
        assert_no_secret_text(&dimensions);
        assert_no_secret_text(&source_metadata);

        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[tokio::test]
    async fn transaction_rollback_prevents_snapshot_persistence()
    -> Result<(), Box<dyn std::error::Error>> {
        let Some(pool) = optional_pool().await? else {
            return Ok(());
        };
        let fixture = seed_fixture(&pool).await?;
        let payload = snapshot_payload(Ga4ReportType::ChannelBreakdown)?;
        let request = request(&fixture, payload);

        let before: i64 = sqlx::query_scalar(
            "select count(*) from project_integration_snapshots where project_id = $1",
        )
        .bind(fixture.project_id)
        .fetch_one(&pool)
        .await?;
        let mut transaction = pool.begin().await?;
        insert_ga4_snapshot_payload(&mut transaction, &request).await?;
        transaction.rollback().await?;
        let after: i64 = sqlx::query_scalar(
            "select count(*) from project_integration_snapshots where project_id = $1",
        )
        .bind(fixture.project_id)
        .fetch_one(&pool)
        .await?;

        assert_eq!(after, before);
        cleanup_fixture(&pool, &fixture).await?;
        Ok(())
    }

    #[test]
    fn invalid_payload_context_and_safe_fields_are_rejected()
    -> Result<(), Box<dyn std::error::Error>> {
        let payload = snapshot_payload(Ga4ReportType::TrafficOverview)?;
        let mut missing_project = Ga4SnapshotInsertRequest::new(
            None,
            Some(Uuid::new_v4()),
            None,
            SnapshotVisibility::Internal,
            SnapshotStatus::Draft,
            payload.clone(),
        );
        assert!(matches!(
            build_ga4_snapshot_insert(&missing_project).unwrap_err(),
            Ga4SnapshotWriteError::MissingProjectContext
        ));

        missing_project.project_id = Some(Uuid::new_v4());
        missing_project.integration_account_id = None;
        assert!(matches!(
            build_ga4_snapshot_insert(&missing_project).unwrap_err(),
            Ga4SnapshotWriteError::MissingIntegrationAccountContext
        ));

        let mut invalid_provider = payload.clone();
        invalid_provider["provider"] = json!("google_analytics");
        assert_writer_error(invalid_provider, Ga4SnapshotWriteError::InvalidProvider);

        let mut invalid_schema = payload.clone();
        invalid_schema["schema_version"] = json!("ga4_snapshot.v0");
        assert_writer_error(invalid_schema, Ga4SnapshotWriteError::InvalidSchemaVersion);

        let mut unsupported_report = payload.clone();
        unsupported_report["report_type"] = json!("unsupported_summary");
        assert_writer_error(
            unsupported_report,
            Ga4SnapshotWriteError::UnsupportedReportType,
        );

        let mut unsafe_payload = payload;
        unsafe_payload["access_token"] = json!("fake-access-token-not-real");
        assert_writer_error(unsafe_payload, Ga4SnapshotWriteError::UnsafePayload);
        Ok(())
    }

    #[test]
    fn helper_does_not_create_sync_or_report_related_payloads()
    -> Result<(), Box<dyn std::error::Error>> {
        let fixture = Fixture {
            client_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            integration_account_id: Uuid::new_v4(),
        };
        let insert = build_ga4_snapshot_insert(&request(
            &fixture,
            snapshot_payload(Ga4ReportType::ConversionsSummary)?,
        ))?;

        assert!(insert.sync_run_id.is_none());
        assert_eq!(
            insert.source_metadata["snapshot_writer"],
            "ga4_snapshot_writer"
        );
        assert_eq!(insert.source_metadata["live_sync"], false);
        assert_no_secret_text(&insert.metrics);
        assert_no_secret_text(&insert.dimensions);
        assert_no_secret_text(&insert.source_metadata);
        Ok(())
    }

    fn assert_writer_error(payload: Value, expected: Ga4SnapshotWriteError) {
        let fixture = Fixture {
            client_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            integration_account_id: Uuid::new_v4(),
        };
        let error = build_ga4_snapshot_insert(&request(&fixture, payload)).unwrap_err();
        assert_eq!(error.to_string(), expected.to_string());
    }

    fn snapshot_payload(report_type: Ga4ReportType) -> Result<Value, Box<dyn std::error::Error>> {
        let reporting_result =
            StubGa4ReportingQueryClient.run_report(&Ga4ReportingQueryRequest::new(
                Some(Uuid::nil()),
                "properties/123456789",
                crate::ga4_reporting::Ga4ReportingDateRange::new(
                    chrono::NaiveDate::from_ymd_opt(2026, 4, 1).expect("date"),
                    chrono::NaiveDate::from_ymd_opt(2026, 4, 30).expect("date"),
                )?,
                None,
                report_type,
            )?)?;
        Ok(transform_ga4_reporting_result_to_snapshot_payload(
            &reporting_result,
            Ga4SnapshotSource::Stub,
        )?)
    }

    fn request(fixture: &Fixture, payload: Value) -> Ga4SnapshotInsertRequest {
        Ga4SnapshotInsertRequest::new(
            Some(fixture.project_id),
            Some(fixture.integration_account_id),
            None,
            SnapshotVisibility::Internal,
            SnapshotStatus::Draft,
            payload,
        )
    }

    struct Fixture {
        client_id: Uuid,
        project_id: Uuid,
        integration_account_id: Uuid,
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

    async fn seed_fixture(pool: &PgPool) -> Result<Fixture, sqlx::Error> {
        let suffix = Uuid::new_v4();
        let client_id: Uuid =
            sqlx::query_scalar("insert into clients (name) values ($1) returning id")
                .bind(format!("GA4 Snapshot Writer Test Client {suffix}"))
                .fetch_one(pool)
                .await?;
        let project_id: Uuid = sqlx::query_scalar(
            "insert into projects (client_id, name, root_domain, allowed_hosts, verification_status)
             values ($1, $2, $3, $4, 'verified') returning id",
        )
        .bind(client_id)
        .bind(format!("GA4 Snapshot Writer Test Project {suffix}"))
        .bind(format!("ga4-writer-{suffix}.example"))
        .bind(Vec::<String>::new())
        .fetch_one(pool)
        .await?;
        let integration_account_id: Uuid = sqlx::query_scalar(
            "insert into integration_accounts
                (provider, account_name, external_account_id, connection_status, metadata)
             values ('google_analytics', $1, $2, 'planned', $3) returning id",
        )
        .bind(format!("GA4 Snapshot Writer Test Account {suffix}"))
        .bind(format!("ga4-writer-test-account-{suffix}"))
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

    fn assert_no_secret_text(value: &Value) {
        let text = value.to_string();
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
                "secret-like field leaked into snapshot writer payload: {forbidden}"
            );
        }
    }
}
