create table integration_accounts (
    id uuid primary key default gen_random_uuid(),
    provider text not null check (
        provider in (
            'monday',
            'google_analytics',
            'google_search_console',
            'google_business_profile',
            'local_falcon',
            'google_ads',
            'quickbooks'
        )
    ),
    account_name text not null,
    external_account_id text,
    connection_status text not null default 'planned' check (
        connection_status in ('planned', 'active', 'paused', 'error', 'disconnected')
    ),
    credentials_ref text,
    metadata jsonb not null default '{}'::jsonb,
    last_sync_at timestamptz,
    created_by uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (provider, external_account_id)
);

create index integration_accounts_provider_idx on integration_accounts(provider);
create index integration_accounts_status_idx on integration_accounts(connection_status);

create table project_integration_accounts (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    integration_account_id uuid not null references integration_accounts(id) on delete cascade,
    resource_type text not null,
    external_resource_id text not null,
    external_resource_name text not null default '',
    sync_enabled boolean not null default false,
    visibility text not null default 'internal' check (visibility in ('internal', 'client')),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (project_id, integration_account_id, resource_type, external_resource_id)
);

create index project_integration_accounts_project_id_idx
    on project_integration_accounts(project_id);
create index project_integration_accounts_account_id_idx
    on project_integration_accounts(integration_account_id);
create index project_integration_accounts_visibility_idx
    on project_integration_accounts(visibility);

create table integration_sync_runs (
    id uuid primary key default gen_random_uuid(),
    integration_account_id uuid references integration_accounts(id) on delete set null,
    project_id uuid references projects(id) on delete cascade,
    provider text not null check (
        provider in (
            'monday',
            'google_analytics',
            'google_search_console',
            'google_business_profile',
            'local_falcon',
            'google_ads',
            'quickbooks'
        )
    ),
    sync_type text not null,
    status text not null default 'queued' check (
        status in ('queued', 'running', 'succeeded', 'failed')
    ),
    started_at timestamptz,
    finished_at timestamptz,
    source_started_at timestamptz,
    source_finished_at timestamptz,
    records_seen integer not null default 0 check (records_seen >= 0),
    records_imported integer not null default 0 check (records_imported >= 0),
    error_message text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index integration_sync_runs_account_created_idx
    on integration_sync_runs(integration_account_id, created_at desc);
create index integration_sync_runs_project_created_idx
    on integration_sync_runs(project_id, created_at desc);
create index integration_sync_runs_provider_status_idx
    on integration_sync_runs(provider, status);

create table project_integration_snapshots (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    integration_account_id uuid references integration_accounts(id) on delete set null,
    sync_run_id uuid references integration_sync_runs(id) on delete set null,
    provider text not null check (
        provider in (
            'monday',
            'google_analytics',
            'google_search_console',
            'google_business_profile',
            'local_falcon',
            'google_ads',
            'quickbooks'
        )
    ),
    snapshot_type text not null check (
        snapshot_type in (
            'monday_board',
            'monday_tasks',
            'ga4_summary',
            'gsc_summary',
            'google_business_profile_summary',
            'local_falcon_summary',
            'google_ads_summary',
            'quickbooks_summary',
            'billing_balance',
            'custom'
        )
    ),
    period_start date,
    period_end date,
    captured_at timestamptz not null default now(),
    visibility text not null default 'internal' check (visibility in ('internal', 'client')),
    status text not null default 'draft' check (status in ('draft', 'published', 'archived')),
    summary text not null default '',
    metrics jsonb not null default '{}'::jsonb,
    dimensions jsonb not null default '{}'::jsonb,
    source_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index project_integration_snapshots_project_captured_idx
    on project_integration_snapshots(project_id, captured_at desc);
create index project_integration_snapshots_provider_type_idx
    on project_integration_snapshots(provider, snapshot_type);
create index project_integration_snapshots_visibility_status_idx
    on project_integration_snapshots(visibility, status);

create table project_report_snapshots (
    project_report_id uuid not null references project_reports(id) on delete cascade,
    project_integration_snapshot_id uuid not null references project_integration_snapshots(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (project_report_id, project_integration_snapshot_id)
);

create index project_report_snapshots_snapshot_id_idx
    on project_report_snapshots(project_integration_snapshot_id);
