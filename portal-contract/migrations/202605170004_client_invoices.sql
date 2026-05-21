create table client_invoices (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references clients(id) on delete cascade,
    project_id uuid references projects(id) on delete set null,
    invoice_number text,
    title text not null,
    description text,
    status text not null default 'open' check (status in ('draft', 'open', 'paid', 'overdue', 'void', 'uncollectible')),
    currency text not null default 'USD',
    amount_cents integer not null default 0 check (amount_cents >= 0),
    balance_cents integer not null default 0 check (balance_cents >= 0),
    issued_at timestamptz,
    due_at timestamptz,
    paid_at timestamptz,
    payment_url text,
    external_provider text,
    external_invoice_id text,
    source_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index client_invoices_client_due_idx on client_invoices(client_id, due_at);
create index client_invoices_project_due_idx on client_invoices(project_id, due_at);
create index client_invoices_client_status_idx on client_invoices(client_id, status);
create index client_invoices_external_idx on client_invoices(external_provider, external_invoice_id);
