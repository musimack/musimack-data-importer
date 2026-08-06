# BigQuery architecture

## Current state

Neither repository contains an operational BigQuery client or query implementation. The Importer has no dataset/project configuration model, service-account query path, cost control, or normalized output contract. The Portal has planning documents and live-weekly vocabulary/storage support for a future `bigquery` provider, but the accepted metric catalog intentionally seeds no BigQuery metrics. Existing property-mapping records include unresolved `TBD` values. No repository evidence establishes production datasets, locations, export configuration, billing ownership, or grants.

BigQuery therefore remains blocked and must not be slipped into the GA4/GSC pilot.

## Ownership and isolation

- The client or its approved Google Cloud project owns the GA4 export and raw dataset.
- The Portal owns the canonical project-to-BigQuery mapping and which normalized metrics are enabled.
- The Importer owns allowlisted queries, dry runs, bytes ceilings, execution, normalization, and reconciliation evidence.
- Google Cloud enforces dataset/table IAM, query-job billing, logging, budgets, and retention configuration.
- The Portal stores only governed normalized weekly observations, not copied raw events.

Prefer one dataset per client/property or an equivalent dataset-level IAM boundary. A shared multi-client raw dataset is rejected unless row-level policies, authorized views, audit evidence, and failure behavior are separately designed and accepted. Do not infer isolation from table names.

## Identity and IAM

Canonical mapping fields:

```text
project_id
provider=bigquery
billing_project_id
source_project_id
dataset_id
dataset_location
allowed_table/view patterns
ga4_property_id correlation
metric contract version
maximum_bytes_billed
retention classification
enabled/pilot state
```

The Cloud Run service account receives `bigquery.jobs.create` in the explicit billing project and dataset-level data-viewer access only to mapped datasets/views. Avoid downloadable keys and broad project-level viewer roles. Where clients cannot grant direct access, use an approved authorized view or client-controlled transfer; do not copy data informally.

## Query guardrails

Every query must have:

- a registered query ID and semantic version;
- parameterized dates/project inputs;
- an allowlisted dataset/table/view pattern;
- a dry run and estimated bytes check before execution;
- an application `maximum_bytes_billed` at or below the approved policy;
- query labels for environment, Portal project UUID, provider, metric contract, week, and run ID using safe values;
- explicit selected columns, partition filters, and no unbounded wildcard scan;
- location matching the mapped dataset;
- one governed purpose and output schema;
- recorded bytes processed/billed and job ID in internal audit evidence;
- no raw row logging or durable raw export by default.

Budgets and alerts are backstops, not request ceilings. A query that exceeds the application ceiling is refused before execution even when the billing budget remains available.

## Metric ownership

GA4 Data API remains authoritative for the initial weekly headline catalog: active users, new users, sessions, views, engaged sessions, engagement rate, average session duration, event count, and key events. Search Console owns clicks, impressions, CTR, and average position.

BigQuery may own approved event-level or business-specific metrics only when their definitions, timezone, attribution, filters, late-arrival behavior, and reconciliation tolerance are accepted. It must not publish a second value under an existing GA4 metric key.

Reconciliation runs may compare like-for-like GA4 Data API and BigQuery measures, but discrepancies are evidence, not an automatic source switch. Record query/schema versions and label one source authoritative for each metric.

## Freshness, late arrivals, and backfill

- Record the newest event date observed and export/table update evidence.
- Treat late-arriving events as a new immutable weekly revision; never mutate an accepted revision.
- Finalization timing must account for the dataset's demonstrated lateness, not only GA4 API availability.
- Backfills use explicit date bounds, request/bytes ceilings, and a separate trigger type.
- Schema changes fail closed until the query adapter and normalization contract support them.
- Partition expiration/retention belongs to the dataset owner; Portal normalized revision retention is a separate policy.

## Cost evidence

For every job retain safe evidence: dry-run estimate, maximum bytes billed, bytes processed/billed, billing project, query ID/version, labels, duration, cache hit where applicable, result row count, and direct-cost estimate/classification. Alert on ceiling refusal, unexpected scan growth, repeated failures, or month-to-date budget thresholds.

## Milestone entry requirements

Before P2-6 BigQuery implementation begins, David must decide dataset ownership, client isolation, billing project, location, retention, allowed metrics, maximum bytes per query/run/month, reconciliation tolerance, and backfill policy. A sanitized inventory of actual datasets and grants is required. Enabling GA4 export, running a query, creating a dataset, or changing IAM is outside this architecture mission.
