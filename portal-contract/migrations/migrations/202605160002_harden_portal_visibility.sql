alter table project_tasks
    add column visibility text not null default 'internal'
    check (visibility in ('internal', 'client'));

create index project_tasks_visibility_idx on project_tasks(visibility);

alter table project_reports
    add column report_type text not null default 'custom'
    check (report_type in ('seo', 'paid_media', 'billing', 'custom'));

create index project_reports_report_type_idx on project_reports(report_type);
