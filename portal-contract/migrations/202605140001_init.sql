create extension if not exists pgcrypto;

do $$ begin
    create type user_role as enum ('admin', 'team_member', 'client_viewer');
exception
    when duplicate_object then null;
end $$;

create table users (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    password_hash text not null,
    role user_role not null default 'client_viewer',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table user_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    session_token text not null unique,
    csrf_token text not null,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);

create index user_sessions_token_idx on user_sessions(session_token);

create table clients (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table projects (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references clients(id) on delete cascade,
    name text not null,
    root_domain text not null,
    allowed_hosts text[] not null default '{}',
    verification_status text not null default 'pending'
        check (verification_status in ('pending', 'verified', 'override_verified', 'failed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index projects_client_id_idx on projects(client_id);

create table domain_verifications (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    method text not null check (method in ('file')),
    token text not null,
    status text not null default 'pending' check (status in ('pending', 'verified', 'failed')),
    created_by uuid references users(id) on delete set null,
    verified_at timestamptz,
    created_at timestamptz not null default now()
);

create index domain_verifications_project_id_idx on domain_verifications(project_id);

create table scans (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    status text not null default 'queued' check (status in ('queued', 'running', 'completed', 'failed')),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    total_sitemap_files integer not null default 0,
    total_discovered_urls integer not null default 0,
    duplicate_urls integer not null default 0,
    invalid_urls integer not null default 0,
    out_of_scope_urls integer not null default 0,
    created_at timestamptz not null default now()
);

create index scans_project_id_idx on scans(project_id);

create table sitemap_files (
    id uuid primary key default gen_random_uuid(),
    scan_id uuid not null references scans(id) on delete cascade,
    url text not null,
    status text not null,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index sitemap_files_scan_id_idx on sitemap_files(scan_id);

create table sitemap_urls (
    id uuid primary key default gen_random_uuid(),
    scan_id uuid not null references scans(id) on delete cascade,
    url text not null,
    lastmod text,
    changefreq text,
    priority real,
    created_at timestamptz not null default now()
);

create index sitemap_urls_scan_id_idx on sitemap_urls(scan_id);
create index sitemap_urls_url_idx on sitemap_urls(url);

create table issues (
    id uuid primary key default gen_random_uuid(),
    scan_id uuid references scans(id) on delete cascade,
    project_id uuid references projects(id) on delete cascade,
    code text not null,
    severity text not null check (severity in ('info', 'warning', 'error')),
    message text not null,
    url text,
    created_at timestamptz not null default now()
);

create index issues_scan_id_idx on issues(scan_id);
create index issues_project_id_idx on issues(project_id);

create table schema_checks (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    url text not null,
    status text not null default 'placeholder',
    requested_by uuid references users(id) on delete set null,
    created_at timestamptz not null default now()
);

create index schema_checks_project_id_idx on schema_checks(project_id);

create table audit_logs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete set null,
    action text not null,
    entity_type text not null,
    entity_id uuid,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index audit_logs_entity_idx on audit_logs(entity_type, entity_id);
