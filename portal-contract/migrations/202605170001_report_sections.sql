create table project_report_sections (
    id uuid primary key default gen_random_uuid(),
    project_report_id uuid not null references project_reports(id) on delete cascade,
    section_key text not null,
    title text not null,
    summary text,
    body text,
    data_json jsonb not null default '{}'::jsonb,
    chart_type text,
    sort_order integer not null default 0,
    visibility text not null default 'internal' check (visibility in ('internal', 'client')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index project_report_sections_report_sort_idx
    on project_report_sections(project_report_id, sort_order);
create index project_report_sections_report_visibility_idx
    on project_report_sections(project_report_id, visibility);
