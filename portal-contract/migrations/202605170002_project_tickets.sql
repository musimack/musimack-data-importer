create table project_tickets (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    submitted_by_user_id uuid references users(id) on delete set null,
    category text not null,
    subject text not null,
    description text not null,
    priority text not null default 'normal' check (priority in ('low', 'normal', 'high', 'urgent')),
    status text not null default 'new' check (status in ('new', 'received', 'in_review', 'in_progress', 'waiting_on_client', 'resolved', 'closed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    closed_at timestamptz
);

create index project_tickets_project_created_idx on project_tickets(project_id, created_at desc);
create index project_tickets_project_status_idx on project_tickets(project_id, status);
create index project_tickets_submitter_created_idx on project_tickets(submitted_by_user_id, created_at desc);
