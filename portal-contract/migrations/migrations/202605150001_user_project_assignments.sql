create table user_project_assignments (
    user_id uuid not null references users(id) on delete cascade,
    project_id uuid not null references projects(id) on delete cascade,
    assigned_by uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    primary key (user_id, project_id)
);

create index user_project_assignments_project_id_idx on user_project_assignments(project_id);
