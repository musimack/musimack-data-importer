create table integration_oauth_states (
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
    user_id uuid not null references users(id) on delete cascade,
    session_id uuid not null references user_sessions(id) on delete cascade,
    state_token text not null unique,
    redirect_uri text not null,
    scopes text[] not null default '{}',
    expires_at timestamptz not null,
    consumed_at timestamptz,
    created_at timestamptz not null default now()
);

create index integration_oauth_states_session_idx
    on integration_oauth_states(session_id, provider, created_at desc);
create index integration_oauth_states_state_idx
    on integration_oauth_states(state_token);
create index integration_oauth_states_expires_at_idx
    on integration_oauth_states(expires_at);
