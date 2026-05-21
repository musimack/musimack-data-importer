create table project_reports (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    title text not null,
    summary text not null default '',
    report_date date,
    status text not null default 'draft' check (status in ('draft', 'published', 'archived')),
    created_by uuid references users(id) on delete set null,
    published_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index project_reports_project_id_idx on project_reports(project_id);
create index project_reports_status_idx on project_reports(status);

create table project_tasks (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    title text not null,
    description text not null default '',
    status text not null default 'open' check (status in ('open', 'in_progress', 'blocked', 'done')),
    priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),
    assigned_to uuid references users(id) on delete set null,
    due_date date,
    created_by uuid references users(id) on delete set null,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index project_tasks_project_id_idx on project_tasks(project_id);
create index project_tasks_assigned_to_idx on project_tasks(assigned_to);
create index project_tasks_status_idx on project_tasks(status);

create table project_notes (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    body text not null,
    visibility text not null default 'client' check (visibility in ('internal', 'client')),
    created_by uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index project_notes_project_id_idx on project_notes(project_id);
create index project_notes_visibility_idx on project_notes(visibility);

create table project_files (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    display_name text not null,
    url text not null,
    content_type text,
    size_bytes bigint,
    visibility text not null default 'client' check (visibility in ('internal', 'client')),
    uploaded_by uuid references users(id) on delete set null,
    created_at timestamptz not null default now()
);

create index project_files_project_id_idx on project_files(project_id);
create index project_files_visibility_idx on project_files(visibility);

create table project_activity (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    actor_id uuid references users(id) on delete set null,
    event_type text not null,
    entity_type text not null,
    entity_id uuid,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index project_activity_project_id_created_at_idx on project_activity(project_id, created_at desc);
create index project_activity_entity_idx on project_activity(entity_type, entity_id);
