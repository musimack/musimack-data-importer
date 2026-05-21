create table project_ticket_comments (
    id uuid primary key default gen_random_uuid(),
    ticket_id uuid not null references project_tickets(id) on delete cascade,
    author_user_id uuid references users(id) on delete set null,
    body text not null,
    visibility text not null default 'client' check (visibility in ('internal', 'client')),
    event_type text not null default 'comment' check (event_type in ('comment', 'status_change', 'priority_change', 'system')),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index project_ticket_comments_ticket_created_idx on project_ticket_comments(ticket_id, created_at);
create index project_ticket_comments_ticket_visibility_idx on project_ticket_comments(ticket_id, visibility);
