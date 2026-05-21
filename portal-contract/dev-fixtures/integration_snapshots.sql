-- Local/demo integration snapshot fixture data only.
-- This file is not a migration and is not run by the application.
-- Apply manually against a local development database:
--
--   psql $env:DATABASE_URL -f dev/fixtures/integration_snapshots.sql
--
-- The API composes response data_json from the summary, metrics, and dimensions columns.
-- Visibility filtering remains enforced by the Rust backend.

begin;

delete from clients
where name in (
    'Musimack Demo Snapshot Client',
    'Cascade Dental Demo',
    'Evergreen Law Demo',
    'Riverside Home Services Demo'
);

delete from integration_accounts
where external_account_id like 'demo-snapshot-%';

with demo_client as (
    insert into clients (name)
    values ('Musimack Demo Snapshot Client')
    returning id
),
demo_project as (
    insert into projects (client_id, name, root_domain, allowed_hosts, verification_status)
    select
        id,
        'Snapshot QA Workspace',
        'snapshot-demo.musimack.local',
        array['snapshot-demo.musimack.local'],
        'verified'
    from demo_client
    returning id
),
demo_report as (
    insert into project_reports (
        project_id,
        title,
        summary,
        report_type,
        report_date,
        status,
        published_at
    )
    select
        id,
        'Snapshot QA Sample Report',
        'Local fixture report for validating linked integration snapshot reads.',
        'custom',
        date '2026-05-01',
        'published',
        now()
    from demo_project
    returning id
),
accounts as (
    insert into integration_accounts (
        provider,
        account_name,
        external_account_id,
        connection_status,
        metadata
    )
    values
        ('google_analytics', 'Demo GA4 Account', 'demo-snapshot-ga4', 'planned', '{"fixture": true}'::jsonb),
        ('google_search_console', 'Demo GSC Property', 'demo-snapshot-gsc', 'planned', '{"fixture": true}'::jsonb),
        ('google_business_profile', 'Demo Business Profile', 'demo-snapshot-gbp', 'planned', '{"fixture": true}'::jsonb),
        ('local_falcon', 'Demo Local Falcon Campaign', 'demo-snapshot-local-falcon', 'planned', '{"fixture": true}'::jsonb),
        ('google_ads', 'Demo Google Ads Account', 'demo-snapshot-google-ads', 'planned', '{"fixture": true}'::jsonb),
        ('monday', 'Demo Monday Board', 'demo-snapshot-monday', 'planned', '{"fixture": true}'::jsonb)
    returning id, provider
),
snapshots as (
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
        demo_project.id,
        accounts.id,
        accounts.provider,
        fixture.snapshot_type,
        fixture.period_start,
        fixture.period_end,
        fixture.captured_at,
        fixture.visibility,
        fixture.status,
        fixture.summary,
        fixture.metrics,
        fixture.dimensions,
        fixture.source_metadata
    from demo_project
    join (
        values
            (
                'google_analytics',
                'ga4_summary',
                date '2026-04-01',
                date '2026-04-30',
                now() - interval '1 day',
                'client',
                'published',
                'Organic traffic increased during the sample reporting period.',
                '[
                    {"name": "users", "value": 1842, "unit": "count"},
                    {"name": "new_users", "value": 1110, "unit": "count"},
                    {"name": "sessions", "value": 2416, "unit": "count"},
                    {"name": "engaged_sessions", "value": 1519, "unit": "count"},
                    {"name": "engagement_rate", "value": 0.629, "unit": "ratio"},
                    {"name": "average_engagement_time_seconds", "value": 83, "unit": "seconds"},
                    {"name": "key_events", "value": 64, "unit": "count"}
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
                        {"name": "key_events", "value": 0, "unit": "count"}
                    ],
                    "primary_channel": "Organic Search",
                    "time_series": [
                        {"date": "2026-04-01", "users": 54, "sessions": 72},
                        {"date": "2026-04-02", "users": 61, "sessions": 80},
                        {"date": "2026-04-03", "users": 58, "sessions": 76},
                        {"date": "2026-04-04", "users": 69, "sessions": 91},
                        {"date": "2026-04-05", "users": 72, "sessions": 95},
                        {"date": "2026-04-06", "users": 66, "sessions": 88},
                        {"date": "2026-04-07", "users": 81, "sessions": 108}
                    ],
                    "dimension_rows": [
                        {
                            "label": "Organic Search",
                            "metrics": [
                                {"name": "sessions", "value": 1044, "unit": "count"},
                                {"name": "key_events", "value": 31, "unit": "count"}
                            ]
                        },
                        {
                            "label": "Direct",
                            "metrics": [
                                {"name": "sessions", "value": 520, "unit": "count"},
                                {"name": "key_events", "value": 11, "unit": "count"}
                            ]
                        },
                        {
                            "label": "Referral",
                            "metrics": [
                                {"name": "sessions", "value": 318, "unit": "count"},
                                {"name": "key_events", "value": 8, "unit": "count"}
                            ]
                        }
                    ]
                }'::jsonb,
                '{
                    "fixture": true,
                    "demo_label": "ga4_overview",
                    "schema_version": "ga4_snapshot.v1",
                    "provider_key": "google_analytics",
                    "source": "local_sql_fixture",
                    "report_type": "channel_breakdown",
                    "property_resource": "properties/123456789",
                    "summary_counts": {
                        "metric_count": 7,
                        "dimension_row_count": 3
                    },
                    "warnings": []
                }'::jsonb
            ),
            (
                'google_search_console',
                'gsc_summary',
                date '2026-04-01',
                date '2026-04-30',
                now() - interval '2 days',
                'client',
                'published',
                'Search visibility improved for a small set of sample queries.',
                '{"clicks": 318, "impressions": 9200, "average_position": 8.7}'::jsonb,
                '{"period_label": "Sample Month", "top_query": "sample service near me"}'::jsonb,
                '{"fixture": true, "demo_label": "gsc_queries"}'::jsonb
            ),
            (
                'google_business_profile',
                'google_business_profile_summary',
                date '2026-04-01',
                date '2026-04-30',
                now() - interval '3 days',
                'client',
                'published',
                'Profile interactions show steady local discovery activity.',
                '{"profile_views": 860, "calls": 37, "direction_requests": 58}'::jsonb,
                '{"period_label": "Sample Month", "location": "Demo Location"}'::jsonb,
                '{"fixture": true, "demo_label": "google_business_profile"}'::jsonb
            ),
            (
                'local_falcon',
                'local_falcon_summary',
                date '2026-04-01',
                date '2026-04-30',
                now() - interval '4 days',
                'internal',
                'published',
                'Local grid rankings need internal review before client delivery.',
                '{"average_rank": 6.4, "grid_points": 49, "top_3_points": 18}'::jsonb,
                '{"period_label": "Sample Month", "keyword": "demo keyword"}'::jsonb,
                '{"fixture": true, "demo_label": "local_falcon"}'::jsonb
            ),
            (
                'google_ads',
                'google_ads_summary',
                date '2026-04-01',
                date '2026-04-30',
                now() - interval '5 days',
                'internal',
                'draft',
                'Paid media numbers are draft fixture data for team review.',
                '{"spend": 1850, "clicks": 740, "conversions": 29}'::jsonb,
                '{"period_label": "Sample Month", "campaign": "Demo Campaign"}'::jsonb,
                '{"fixture": true, "demo_label": "google_ads_overview"}'::jsonb
            ),
            (
                'monday',
                'monday_tasks',
                date '2026-04-01',
                date '2026-04-30',
                now() - interval '6 days',
                'client',
                'archived',
                'Archived sample task delivery snapshot for historical QA.',
                '{"open_items": 7, "completed_items": 18, "blocked_items": 1}'::jsonb,
                '{"period_label": "Sample Month", "board": "Demo Delivery Board"}'::jsonb,
                '{"fixture": true, "demo_label": "monday_tasks"}'::jsonb
            )
    ) as fixture (
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
        on true
    join accounts on accounts.provider = fixture.provider
    returning id
)
insert into project_report_snapshots (project_report_id, project_integration_snapshot_id)
select demo_report.id, snapshots.id
from demo_report
cross join snapshots;

commit;

begin;

with demo_definitions as (
    select *
    from (
        values
            (
                'Cascade Dental Demo',
                'Dental Website Reporting',
                'cascade-dental-demo.musimack.local',
                'April Website Performance Report',
                'Local fake GA4 report path for dental website performance QA.',
                'Cascade Dental Demo GA4 Account',
                'demo-snapshot-ga4-cascade-dental',
                'Dental website traffic improved across visits, engaged visits, and key actions in this fake reporting period.',
                '[
                    {"name": "users", "value": 1264, "unit": "count"},
                    {"name": "new_users", "value": 842, "unit": "count"},
                    {"name": "sessions", "value": 1718, "unit": "count"},
                    {"name": "engaged_sessions", "value": 1132, "unit": "count"},
                    {"name": "engagement_rate", "value": 0.659, "unit": "ratio"},
                    {"name": "average_engagement_time_seconds", "value": 96, "unit": "seconds"},
                    {"name": "key_events", "value": 48, "unit": "count"},
                    {"name": "conversions", "value": 48, "unit": "count"},
                    {"name": "views", "value": 4380, "unit": "count"}
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
                        {"name": "users", "value": 1120, "unit": "count"},
                        {"name": "new_users", "value": 760, "unit": "count"},
                        {"name": "sessions", "value": 1510, "unit": "count"},
                        {"name": "engaged_sessions", "value": 960, "unit": "count"},
                        {"name": "engagement_rate", "value": 0.636, "unit": "ratio"},
                        {"name": "average_engagement_time_seconds", "value": 82, "unit": "seconds"},
                        {"name": "key_events", "value": 36, "unit": "count"},
                        {"name": "conversions", "value": 36, "unit": "count"}
                    ],
                    "time_series": [
                        {"date": "2026-04-01", "users": 39, "sessions": 54},
                        {"date": "2026-04-02", "users": 44, "sessions": 61},
                        {"date": "2026-04-03", "users": 47, "sessions": 65},
                        {"date": "2026-04-04", "users": 50, "sessions": 68},
                        {"date": "2026-04-05", "users": 53, "sessions": 72},
                        {"date": "2026-04-06", "users": 57, "sessions": 78},
                        {"date": "2026-04-07", "users": 61, "sessions": 83}
                    ],
                    "dimension_rows": [
                        {
                            "label": "Organic Search",
                            "metrics": [
                                {"name": "sessions", "value": 736, "unit": "count"},
                                {"name": "users", "value": 548, "unit": "count"},
                                {"name": "key_events", "value": 24, "unit": "count"}
                            ]
                        },
                        {
                            "label": "Direct",
                            "metrics": [
                                {"name": "sessions", "value": 381, "unit": "count"},
                                {"name": "users", "value": 292, "unit": "count"},
                                {"name": "key_events", "value": 9, "unit": "count"}
                            ]
                        },
                        {
                            "label": "Referral",
                            "metrics": [
                                {"name": "sessions", "value": 244, "unit": "count"},
                                {"name": "users", "value": 176, "unit": "count"},
                                {"name": "key_events", "value": 7, "unit": "count"}
                            ]
                        }
                    ]
                }'::jsonb,
                '{
                    "fixture": true,
                    "demo_label": "ga4_multi_client_cascade_dental",
                    "schema_version": "ga4_snapshot.v1",
                    "provider_key": "google_analytics",
                    "source": "local_sql_fixture",
                    "report_type": "channel_breakdown",
                    "property_resource": "properties/223456789",
                    "summary_counts": {
                        "metric_count": 9,
                        "dimension_row_count": 3
                    },
                    "warnings": []
                }'::jsonb
            ),
            (
                'Evergreen Law Demo',
                'Law Firm Website Reporting',
                'evergreen-law-demo.musimack.local',
                'April Website Performance Report',
                'Local fake GA4 report path for law firm website performance QA.',
                'Evergreen Law Demo GA4 Account',
                'demo-snapshot-ga4-evergreen-law',
                'Law firm website traffic had mixed movement in this fake reporting period, with visits up and key actions flat.',
                '[
                    {"name": "users", "value": 934, "unit": "count"},
                    {"name": "new_users", "value": 612, "unit": "count"},
                    {"name": "sessions", "value": 1288, "unit": "count"},
                    {"name": "engaged_sessions", "value": 708, "unit": "count"},
                    {"name": "engagement_rate", "value": 0.550, "unit": "ratio"},
                    {"name": "average_engagement_time_seconds", "value": 74, "unit": "seconds"},
                    {"name": "key_events", "value": 22, "unit": "count"},
                    {"name": "conversions", "value": 22, "unit": "count"},
                    {"name": "views", "value": 3564, "unit": "count"}
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
                        {"name": "users", "value": 900, "unit": "count"},
                        {"name": "new_users", "value": 640, "unit": "count"},
                        {"name": "sessions", "value": 1180, "unit": "count"},
                        {"name": "engaged_sessions", "value": 720, "unit": "count"},
                        {"name": "engagement_rate", "value": 0.610, "unit": "ratio"},
                        {"name": "average_engagement_time_seconds", "value": 74, "unit": "seconds"},
                        {"name": "key_events", "value": 22, "unit": "count"},
                        {"name": "conversions", "value": 22, "unit": "count"}
                    ],
                    "time_series": [
                        {"date": "2026-04-01", "users": 32, "sessions": 45},
                        {"date": "2026-04-02", "users": 35, "sessions": 48},
                        {"date": "2026-04-03", "users": 28, "sessions": 41},
                        {"date": "2026-04-04", "users": 31, "sessions": 44},
                        {"date": "2026-04-05", "users": 36, "sessions": 50},
                        {"date": "2026-04-06", "users": 33, "sessions": 47},
                        {"date": "2026-04-07", "users": 39, "sessions": 54}
                    ],
                    "dimension_rows": [
                        {
                            "label": "Home",
                            "metrics": [
                                {"name": "views", "value": 980, "unit": "count"},
                                {"name": "users", "value": 402, "unit": "count"}
                            ]
                        },
                        {
                            "label": "Practice Areas",
                            "metrics": [
                                {"name": "views", "value": 744, "unit": "count"},
                                {"name": "users", "value": 286, "unit": "count"}
                            ]
                        },
                        {
                            "label": "Contact",
                            "metrics": [
                                {"name": "views", "value": 412, "unit": "count"},
                                {"name": "users", "value": 171, "unit": "count"},
                                {"name": "key_events", "value": 8, "unit": "count"}
                            ]
                        }
                    ]
                }'::jsonb,
                '{
                    "fixture": true,
                    "demo_label": "ga4_multi_client_evergreen_law",
                    "schema_version": "ga4_snapshot.v1",
                    "provider_key": "google_analytics",
                    "source": "local_sql_fixture",
                    "report_type": "top_pages",
                    "property_resource": "properties/323456789",
                    "summary_counts": {
                        "metric_count": 9,
                        "dimension_row_count": 3
                    },
                    "warnings": []
                }'::jsonb
            ),
            (
                'Riverside Home Services Demo',
                'Home Services Reporting',
                'riverside-home-demo.musimack.local',
                'April Website Performance Report',
                'Local fake GA4 report path for sparse home services website performance QA.',
                'Riverside Home Services Demo GA4 Account',
                'demo-snapshot-ga4-riverside-home',
                'Home services website reporting uses a sparse fake dataset for fallback and missing-comparison QA.',
                '[
                    {"name": "users", "value": 512, "unit": "count"},
                    {"name": "sessions", "value": 688, "unit": "count"},
                    {"name": "engaged_sessions", "value": 344, "unit": "count"},
                    {"name": "engagement_rate", "value": 0.500, "unit": "ratio"},
                    {"name": "average_engagement_time_seconds", "value": 58, "unit": "seconds"},
                    {"name": "key_events", "value": 0, "unit": "count"}
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
                        {"name": "users", "value": 498, "unit": "count"},
                        {"name": "sessions", "value": 0, "unit": "count"},
                        {"name": "engaged_sessions", "value": 344, "unit": "count"},
                        {"name": "engagement_rate", "value": 0.480, "unit": "ratio"},
                        {"name": "average_engagement_time_seconds", "value": 62, "unit": "seconds"}
                    ],
                    "time_series": [
                        {"date": "2026-04-01", "users": 15, "sessions": 20},
                        {"date": "2026-04-02", "users": 18, "sessions": 24},
                        {"date": "2026-04-03", "users": 14, "sessions": 18},
                        {"date": "2026-04-04", "users": 21, "sessions": 29},
                        {"date": "2026-04-05", "users": 17, "sessions": 23}
                    ],
                    "dimension_rows": [
                        {
                            "label": "Organic Search",
                            "metrics": [
                                {"name": "sessions", "value": 302, "unit": "count"},
                                {"name": "users", "value": 226, "unit": "count"}
                            ]
                        },
                        {
                            "label": "Direct",
                            "metrics": [
                                {"name": "sessions", "value": 184, "unit": "count"},
                                {"name": "users", "value": 139, "unit": "count"}
                            ]
                        }
                    ]
                }'::jsonb,
                '{
                    "fixture": true,
                    "demo_label": "ga4_multi_client_riverside_home",
                    "schema_version": "ga4_snapshot.v1",
                    "provider_key": "google_analytics",
                    "source": "local_sql_fixture",
                    "report_type": "channel_breakdown",
                    "property_resource": "properties/423456789",
                    "summary_counts": {
                        "metric_count": 6,
                        "dimension_row_count": 2
                    },
                    "warnings": ["Sparse fake data for local display fallback QA."]
                }'::jsonb
            )
    ) as fixture (
        client_name,
        project_name,
        root_domain,
        report_title,
        report_summary,
        account_name,
        external_account_id,
        snapshot_summary,
        metrics,
        dimensions,
        source_metadata
    )
),
demo_clients as (
    insert into clients (name)
    select client_name
    from demo_definitions
    returning id, name
),
demo_projects as (
    insert into projects (client_id, name, root_domain, allowed_hosts, verification_status)
    select
        demo_clients.id,
        demo_definitions.project_name,
        demo_definitions.root_domain,
        array[demo_definitions.root_domain],
        'verified'
    from demo_definitions
    join demo_clients on demo_clients.name = demo_definitions.client_name
    returning id, client_id, name
),
demo_reports as (
    insert into project_reports (
        project_id,
        title,
        summary,
        report_type,
        report_date,
        status,
        published_at
    )
    select
        demo_projects.id,
        demo_definitions.report_title,
        demo_definitions.report_summary,
        'custom',
        date '2026-05-01',
        'published',
        now()
    from demo_definitions
    join demo_clients on demo_clients.name = demo_definitions.client_name
    join demo_projects on demo_projects.client_id = demo_clients.id
        and demo_projects.name = demo_definitions.project_name
    returning id, project_id, title
),
ga4_accounts as (
    insert into integration_accounts (
        provider,
        account_name,
        external_account_id,
        connection_status,
        metadata
    )
    select
        'google_analytics',
        account_name,
        external_account_id,
        'planned',
        jsonb_build_object('fixture', true, 'demo_client', client_name)
    from demo_definitions
    returning id, external_account_id
),
ga4_snapshots as (
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
        demo_projects.id,
        ga4_accounts.id,
        'google_analytics',
        'ga4_summary',
        date '2026-04-01',
        date '2026-04-30',
        now() - interval '1 day',
        'client',
        'published',
        demo_definitions.snapshot_summary,
        demo_definitions.metrics,
        demo_definitions.dimensions,
        demo_definitions.source_metadata
    from demo_definitions
    join demo_clients on demo_clients.name = demo_definitions.client_name
    join demo_projects on demo_projects.client_id = demo_clients.id
        and demo_projects.name = demo_definitions.project_name
    join ga4_accounts on ga4_accounts.external_account_id = demo_definitions.external_account_id
    returning id, project_id
)
insert into project_report_snapshots (project_report_id, project_integration_snapshot_id)
select demo_reports.id, ga4_snapshots.id
from demo_reports
join ga4_snapshots on ga4_snapshots.project_id = demo_reports.project_id;

commit;
