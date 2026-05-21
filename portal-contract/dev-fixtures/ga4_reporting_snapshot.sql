-- Local/demo GA4 reporting snapshot fixture data only.
-- This file is not a migration and is not run by the application.
-- Apply after dev/fixtures/integration_snapshots.sql:
--
--   psql $env:DATABASE_URL -f dev/fixtures/ga4_reporting_snapshot.sql
--
-- The fixture targets the demo project, GA4 account, and report created by
-- integration_snapshots.sql. It models a future GA4 Data API import shape
-- without adding OAuth, credentials, live API calls, or background sync.

begin;

with demo_context as (
    select
        p.id as project_id,
        r.id as report_id,
        ia.id as integration_account_id
    from projects p
    join clients c on c.id = p.client_id
    join project_reports r on r.project_id = p.id
    join integration_accounts ia on ia.provider = 'google_analytics'
        and ia.external_account_id = 'demo-snapshot-ga4'
    where c.name = 'Musimack Demo Snapshot Client'
      and p.name = 'Snapshot QA Workspace'
      and r.title = 'Snapshot QA Sample Report'
),
delete_existing_sections as (
    delete from project_report_sections
    where project_report_id in (select report_id from demo_context)
      and section_key in (
          'ga4_website_performance_summary',
          'ga4_traffic_and_engagement',
          'ga4_top_pages',
          'ga4_channel_breakdown',
          'ga4_conversion_activity',
          'ga4_next_actions'
      )
    returning id
),
delete_existing_snapshots as (
    delete from project_integration_snapshots
    where project_id in (select project_id from demo_context)
      and provider = 'google_analytics'
      and snapshot_type = 'ga4_summary'
      and source_metadata->>'demo_label' = 'ga4_reporting_mock_import'
    returning id
),
ga4_snapshot as (
    insert into project_integration_snapshots (
        project_id,
        integration_account_id,
        provider,
        snapshot_type,
        period_start,
        period_end,
        captured_at,
        visibility,
        status,
        summary,
        metrics,
        dimensions,
        source_metadata
    )
    select
        demo_context.project_id,
        demo_context.integration_account_id,
        'google_analytics',
        'ga4_summary',
        date '2026-04-01',
        date '2026-04-30',
        now(),
        'client',
        'published',
        'Website traffic and engagement improved in this fake GA4 reporting period.',
        '[
            {"name": "users", "value": 1842, "unit": "count"},
            {"name": "new_users", "value": 1110, "unit": "count"},
            {"name": "sessions", "value": 2416, "unit": "count"},
            {"name": "engaged_sessions", "value": 1519, "unit": "count"},
            {"name": "engagement_rate", "value": 0.629, "unit": "ratio"},
            {"name": "average_engagement_time_seconds", "value": 83, "unit": "seconds"},
            {"name": "key_events", "value": 64, "unit": "count"},
            {"name": "conversions", "value": 64, "unit": "count"},
            {"name": "views", "value": 6128, "unit": "count"}
        ]'::jsonb,
        '{
            "date_range": {
                "period_label": "April 2026",
                "start_date": "2026-04-01",
                "end_date": "2026-04-30"
            },
            "comparison_date_range": {
                "period_label": "March 2026",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31"
            },
            "previous_metrics": [
                {"name": "users", "value": 1700, "unit": "count"},
                {"name": "new_users", "value": 1000, "unit": "count"},
                {"name": "sessions", "value": 2200, "unit": "count"},
                {"name": "engaged_sessions", "value": 1400, "unit": "count"},
                {"name": "engagement_rate", "value": 0.600, "unit": "ratio"},
                {"name": "average_engagement_time_seconds", "value": 70, "unit": "seconds"},
                {"name": "key_events", "value": 0, "unit": "count"},
                {"name": "conversions", "value": 0, "unit": "count"}
            ],
            "time_series": [
                {"date": "2026-04-01", "users": 54, "sessions": 72, "new_users": 32, "key_events": 3},
                {"date": "2026-04-02", "users": 61, "sessions": 80, "new_users": 37, "key_events": 4},
                {"date": "2026-04-03", "users": 58, "sessions": 76, "new_users": 34, "key_events": 5},
                {"date": "2026-04-04", "users": 69, "sessions": 91, "new_users": 43, "key_events": 6},
                {"date": "2026-04-05", "users": 72, "sessions": 95, "new_users": 44, "key_events": 7},
                {"date": "2026-04-06", "users": 66, "sessions": 88, "new_users": 39, "key_events": 5},
                {"date": "2026-04-07", "users": 81, "sessions": 108, "new_users": 50, "key_events": 8}
            ],
            "top_pages": [
                {"page": "/", "title": "Home", "views": 1420, "users": 740, "engagement_rate": "66.1%"},
                {"page": "/services", "title": "Services", "views": 980, "users": 511, "engagement_rate": "61.4%"},
                {"page": "/contact", "title": "Contact", "views": 612, "users": 295, "engagement_rate": "70.2%"},
                {"page": "/blog/sample-guide", "title": "Sample Guide", "views": 438, "users": 214, "engagement_rate": "58.0%"}
            ],
            "traffic_channels": [
                {"channel": "Organic Search", "sessions": 1044, "users": 820, "conversions": 31},
                {"channel": "Direct", "sessions": 520, "users": 430, "conversions": 11},
                {"channel": "Referral", "sessions": 318, "users": 250, "conversions": 8},
                {"channel": "Paid Search", "sessions": 280, "users": 221, "conversions": 10},
                {"channel": "Organic Social", "sessions": 254, "users": 194, "conversions": 4}
            ],
            "dimension_rows": [
                {
                    "label": "Organic Search",
                    "metrics": [
                        {"name": "sessions", "value": 1044, "unit": "count"},
                        {"name": "users", "value": 820, "unit": "count"},
                        {"name": "key_events", "value": 31, "unit": "count"}
                    ]
                },
                {
                    "label": "Direct",
                    "metrics": [
                        {"name": "sessions", "value": 520, "unit": "count"},
                        {"name": "users", "value": 430, "unit": "count"},
                        {"name": "key_events", "value": 11, "unit": "count"}
                    ]
                },
                {
                    "label": "Referral",
                    "metrics": [
                        {"name": "sessions", "value": 318, "unit": "count"},
                        {"name": "users", "value": 250, "unit": "count"},
                        {"name": "key_events", "value": 8, "unit": "count"}
                    ]
                },
                {
                    "label": "Paid Search",
                    "metrics": [
                        {"name": "sessions", "value": 280, "unit": "count"},
                        {"name": "users", "value": 221, "unit": "count"},
                        {"name": "key_events", "value": 10, "unit": "count"}
                    ]
                }
            ],
            "device_breakdown": [
                {"device": "mobile", "sessions": 1328, "share": "55.0%"},
                {"device": "desktop", "sessions": 917, "share": "38.0%"},
                {"device": "tablet", "sessions": 171, "share": "7.0%"}
            ]
        }'::jsonb,
        '{
            "fixture": true,
            "demo_label": "ga4_reporting_mock_import",
            "schema_version": "ga4_snapshot.v1",
            "provider_key": "google_analytics",
            "source": "local_sql_fixture",
            "report_type": "channel_breakdown",
            "property_resource": "properties/123456789",
            "summary_counts": {
                "metric_count": 9,
                "dimension_row_count": 4
            },
            "warnings": []
        }'::jsonb
    from demo_context
    returning id
),
link_snapshot as (
    insert into project_report_snapshots (
        project_report_id,
        project_integration_snapshot_id
    )
    select demo_context.report_id, ga4_snapshot.id
    from demo_context
    cross join ga4_snapshot
    on conflict do nothing
    returning project_report_id
)
insert into project_report_sections (
    project_report_id,
    section_key,
    title,
    summary,
    body,
    data_json,
    chart_type,
    sort_order,
    visibility
)
select
    demo_context.report_id,
    fixture.section_key,
    fixture.title,
    fixture.summary,
    fixture.body,
    fixture.data_json,
    fixture.chart_type,
    fixture.sort_order,
    'client'
from demo_context
join (
    values
        (
            'ga4_website_performance_summary',
            'Website Performance Summary',
            'A fake client-facing GA4 summary for the reporting period.',
            'This section models the high-level website performance narrative that a future GA4 sync can populate from local snapshots.',
            '{
                "metrics": {
                    "users": 1842,
                    "sessions": 2416,
                    "engaged_sessions": 1519,
                    "engagement_rate": "62.9%",
                    "conversions": 64,
                    "views": 6128
                },
                "time_series": [
                    {"date": "2026-04-01", "users": 54, "sessions": 72},
                    {"date": "2026-04-02", "users": 61, "sessions": 80},
                    {"date": "2026-04-03", "users": 58, "sessions": 76},
                    {"date": "2026-04-04", "users": 69, "sessions": 91},
                    {"date": "2026-04-05", "users": 72, "sessions": 95},
                    {"date": "2026-04-06", "users": 66, "sessions": 88},
                    {"date": "2026-04-07", "users": 81, "sessions": 108}
                ]
            }'::jsonb,
            'metric_cards',
            110
        ),
        (
            'ga4_traffic_and_engagement',
            'Traffic and Engagement',
            'Fake engagement metrics designed for generic report rendering.',
            'Sessions and engaged sessions increased in this sample period, with engagement rate staying above the demo benchmark.',
            '{
                "metrics": {
                    "sessions": 2416,
                    "engaged_sessions": 1519,
                    "engagement_rate": "62.9%",
                    "event_count": 18430
                },
                "time_series": [
                    {"date": "2026-04-01", "users": 54, "sessions": 72},
                    {"date": "2026-04-02", "users": 61, "sessions": 80},
                    {"date": "2026-04-03", "users": 58, "sessions": 76},
                    {"date": "2026-04-04", "users": 69, "sessions": 91},
                    {"date": "2026-04-05", "users": 72, "sessions": 95},
                    {"date": "2026-04-06", "users": 66, "sessions": 88},
                    {"date": "2026-04-07", "users": 81, "sessions": 108}
                ],
                "rows": [
                    {"metric": "Users", "value": 1842, "note": "Fake GA4 active users"},
                    {"metric": "Sessions", "value": 2416, "note": "Fake GA4 sessions"},
                    {"metric": "Engaged sessions", "value": 1519, "note": "Fake engaged sessions"}
                ]
            }'::jsonb,
            'table',
            120
        ),
        (
            'ga4_top_pages',
            'Top Pages',
            'Fake page-level performance rows for report table QA.',
            'The pages below are generic examples and do not represent real analytics data.',
            '{
                "rows": [
                    {"page": "/", "title": "Home", "views": 1420, "users": 740, "engagement_rate": "66.1%"},
                    {"page": "/services", "title": "Services", "views": 980, "users": 511, "engagement_rate": "61.4%"},
                    {"page": "/contact", "title": "Contact", "views": 612, "users": 295, "engagement_rate": "70.2%"},
                    {"page": "/blog/sample-guide", "title": "Sample Guide", "views": 438, "users": 214, "engagement_rate": "58.0%"}
                ]
            }'::jsonb,
            'table',
            130
        ),
        (
            'ga4_channel_breakdown',
            'Channel Breakdown',
            'Fake acquisition channel mix for client-facing reporting QA.',
            'Organic Search leads the sample period, followed by Direct and Referral traffic.',
            '{
                "rows": [
                    {"channel": "Organic Search", "sessions": 1044, "users": 820, "conversions": 31},
                    {"channel": "Direct", "sessions": 520, "users": 430, "conversions": 11},
                    {"channel": "Referral", "sessions": 318, "users": 250, "conversions": 8},
                    {"channel": "Paid Search", "sessions": 280, "users": 221, "conversions": 10},
                    {"channel": "Organic Social", "sessions": 254, "users": 194, "conversions": 4}
                ]
            }'::jsonb,
            'bar',
            140
        ),
        (
            'ga4_conversion_activity',
            'Conversion Activity',
            'Fake conversion and key event totals for report metric QA.',
            'The portal should show these as report-ready client summaries, not a raw analytics dashboard.',
            '{
                "metrics": {
                    "conversions": 64,
                    "key_events": 64,
                    "event_count": 18430
                },
                "rows": [
                    {"event": "generate_lead", "count": 34},
                    {"event": "form_submit", "count": 18},
                    {"event": "click_to_call", "count": 12}
                ]
            }'::jsonb,
            'metric_cards',
            150
        ),
        (
            'ga4_next_actions',
            'Recommended Next Actions',
            'Sample recommendations based on the fake GA4 fixture.',
            'These recommendations are local demo content for validating the client report layout.',
            '{
                "items": [
                    "Review the highest-engagement service pages for conversion opportunities.",
                    "Compare Organic Search and Direct traffic quality in the next reporting period.",
                    "Confirm key event definitions before enabling a live GA4 sync.",
                    "Prepare a client-facing summary instead of exposing raw analytics tables."
                ]
            }'::jsonb,
            'checklist',
            160
        )
) as fixture (
    section_key,
    title,
    summary,
    body,
    data_json,
    chart_type,
    sort_order
)
    on true;

commit;
