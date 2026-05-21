create table integration_credentials (
    id uuid primary key default gen_random_uuid(),
    integration_account_id uuid not null references integration_accounts(id) on delete cascade,
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
    credential_kind text not null check (
        credential_kind in ('oauth_token', 'api_key', 'service_account', 'other')
    ),
    encrypted_payload bytea not null,
    encryption_key_version text not null,
    scopes text[] not null default '{}',
    expires_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index integration_credentials_account_id_idx
    on integration_credentials(integration_account_id);
create index integration_credentials_provider_idx
    on integration_credentials(provider);
create index integration_credentials_expires_at_idx
    on integration_credentials(expires_at);
