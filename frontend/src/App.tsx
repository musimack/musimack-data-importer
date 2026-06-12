import { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8765';

type ProviderReadiness = {
  provider: string;
  label: string;
  enabled: boolean;
  config_ready: boolean;
  credentials_ready: boolean;
  expected_output_file: string;
  output_file_exists: boolean;
  readiness: {
    config_present: boolean;
    credentials_present: boolean;
  };
};

type OutputFileStatus = {
  file: string;
  exists: boolean;
  last_modified: string;
  size: string;
  schema_version: string;
  json_valid: boolean | null;
  warning: string;
};

type OutputStatus = {
  folder_exists: boolean;
  ok: boolean;
  warnings: string[];
  expected_files: string[];
  files: OutputFileStatus[];
};

type ActionPlanItem = {
  id: string;
  label: string;
  provider: string;
  status: string;
  blocked_reason: string | null;
  command: string;
  expected_output: string;
  missing_inputs: string[];
  safety_notes: string[];
  manual_step: string;
  readiness: Record<string, boolean | string>;
};

type ActionPlan = {
  profile_slug: string;
  actions: ActionPlanItem[];
};

type ValidationRunResult = {
  action_id: string;
  profile_slug: string;
  status: string;
  duration_ms: number;
  result: {
    folder: string;
    folder_exists: boolean;
    expected_files: string[];
    required_files: string[];
    files: Array<OutputFileStatus & { required: boolean }>;
    missing_files: string[];
    missing_required_files: string[];
    missing_disabled_provider_files: string[];
    malformed_json_files: string[];
    warnings: string[];
    overall_status: string;
  };
  audit: {
    logged: boolean;
    path: string;
    error?: string;
  };
  guardrails: string[];
};

type CopyPlanItem = {
  file: string;
  source: string;
  source_exists: boolean;
  destination: string;
  destination_exists: boolean;
  action: string;
  size: string;
  last_modified: string;
};

type CopyPreview = {
  action_id: string;
  profile_slug: string;
  source_folder: string;
  destination_folder: string;
  expected_files: string[];
  items: CopyPlanItem[];
  guardrails: string[];
};

type CopyResultItem = CopyPlanItem & {
  status: string;
  error: string;
};

type CopyRunResult = {
  action_id: string;
  profile_slug: string;
  status: string;
  duration_ms: number;
  source_folder: string;
  destination_folder: string;
  items: CopyResultItem[];
  counts: Record<string, number>;
  warnings: string[];
  audit: {
    logged: boolean;
    path: string;
    error?: string;
  };
  guardrails: string[];
};

type ActionRunEntry = {
  audit_entry_id: string;
  timestamp: string;
  action_id: string;
  profile_slug: string;
  status: string;
  result_summary: Record<string, boolean | number | string | null>;
  file_counts: Record<string, boolean | number | string | null>;
  warnings: string[];
  warnings_count: number;
  duration_ms: number | null;
};

type ActionRunHistory = {
  entries: ActionRunEntry[];
  count: number;
  skipped_malformed: number;
};

type LastActions = {
  last_action: ActionRunEntry | null;
  last_validation: ActionRunEntry | null;
  last_copy: ActionRunEntry | null;
  skipped_malformed: number;
};

type ProfileCapability = {
  key: string;
  label: string;
  status: string;
  kind: string;
  provider: string;
  expected_output_file: string;
  notes: string;
};

type ProviderSetupChecklistItem = {
  provider_key: string;
  provider_label: string;
  expected_output_file: string;
  output_exists: boolean;
  local_output_state: string;
  dashboard_lab_writer_status: string;
  required_config_items: string[];
  local_config_file_present: boolean;
  local_config_path_label: string;
  local_config_valid: boolean;
  local_config_error: string;
  config_state: Record<string, boolean>;
  config_visible: boolean;
  missing_config_details: string[];
  safe_next_action: string;
  blocked_reason: string;
  status: string;
  severity: string;
  capability_status: string;
  supported_in_console: boolean;
  validation_ready: string;
  dashboard_copy_ready: string;
  validate_readiness: string;
  dashboard_copy_readiness: string;
};

type GuardedImportPhase = {
  phase: string;
  label: string;
  providers: Array<Record<string, string | boolean>>;
  network_allowed: boolean;
  copy_allowed: boolean;
  notes: string[];
};

type ProfileSummary = {
  slug: string;
  display_name: string;
  domain: string;
  vertical: string;
  service_model: string;
  dashboard_lab_route: string;
  enabled_providers: string[];
  capabilities: ProfileCapability[];
  provider_readiness: ProviderReadiness[];
  provider_setup_checklist: ProviderSetupChecklistItem[];
};

type ProfileDetail = ProfileSummary & {
  paths: {
    local_real_output_folder: string;
    dashboard_lab_local_fixture_folder: string;
  };
  output_status: OutputStatus;
  action_plan: ActionPlan;
  guarded_import_sequence: {
    profile_slug: string;
    phases: GuardedImportPhase[];
  };
  last_actions: LastActions;
  safety: {
    read_only: boolean;
    local_only: boolean;
    real_output_ignored_path: string;
    dashboard_lab_local_fixtures_only: boolean;
  };
};

function App() {
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string>('');
  const [detail, setDetail] = useState<ProfileDetail | null>(null);
  const [error, setError] = useState<string>('');
  const [copiedActionId, setCopiedActionId] = useState<string>('');
  const [validationConfirmed, setValidationConfirmed] = useState<boolean>(false);
  const [validationResult, setValidationResult] = useState<ValidationRunResult | null>(null);
  const [validationRunning, setValidationRunning] = useState<boolean>(false);
  const [copyPreview, setCopyPreview] = useState<CopyPreview | null>(null);
  const [copyConfirmed, setCopyConfirmed] = useState<boolean>(false);
  const [copyResult, setCopyResult] = useState<CopyRunResult | null>(null);
  const [copyRunning, setCopyRunning] = useState<boolean>(false);
  const [actionHistory, setActionHistory] = useState<ActionRunHistory | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.slug === selectedSlug),
    [profiles, selectedSlug],
  );

  useEffect(() => {
    fetch(`${API_BASE}/api/profiles`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        return response.json();
      })
      .then((payload: { profiles: ProfileSummary[] }) => {
        setProfiles(payload.profiles);
        setSelectedSlug(payload.profiles[0]?.slug ?? '');
      })
      .catch((fetchError: Error) => setError(fetchError.message));
  }, []);

  useEffect(() => {
    if (!selectedSlug) {
        setDetail(null);
      setValidationConfirmed(false);
      setValidationResult(null);
      setCopyPreview(null);
      setCopyConfirmed(false);
      setCopyResult(null);
      setActionHistory(null);
      return;
    }
    setValidationConfirmed(false);
    setValidationResult(null);
    setCopyPreview(null);
    setCopyConfirmed(false);
    setCopyResult(null);
    setActionHistory(null);
    refreshProfileStatus(
      selectedSlug,
      setDetail,
      setCopyPreview,
      setActionHistory,
      setError,
      setRefreshing,
      setStatusMessage,
    );
  }, [selectedSlug]);

  const refreshSelectedProfile = (message = 'Profile status refreshed') => {
    if (!selectedSlug) {
      return;
    }
    refreshProfileStatus(
      selectedSlug,
      setDetail,
      setCopyPreview,
      setActionHistory,
      setError,
      setRefreshing,
      setStatusMessage,
      message,
    );
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Musimack Data Importer Console</h1>
          <p>Local read-only admin foundation for client profiles and data-source readiness.</p>
        </div>
        <span className="status-pill">Local only</span>
      </header>

      <section className="safety-notice" aria-label="Safety boundary notice">
        <strong>Safety boundary:</strong> real data stays in ignored local folders. Do not commit{' '}
        <code>exports/local-real/</code> or dashboard-lab <code>public/local-fixtures/</code>. No staging,
        production, portal database, OAuth, upload, or provider mutation actions happen here.
      </section>

      {error ? <div className="error-banner">API error: {error}</div> : null}

      <div className="workspace">
        <aside className="client-list" aria-label="Client profiles">
          <h2>Clients</h2>
          {profiles.map((profile) => (
            <button
              key={profile.slug}
              type="button"
              className={profile.slug === selectedSlug ? 'client-button active' : 'client-button'}
              onClick={() => setSelectedSlug(profile.slug)}
            >
              <span>{profile.display_name}</span>
              <small>{profile.domain}</small>
            </button>
          ))}
        </aside>

        <section className="detail-panel">
          {detail ? (
            <>
              <div className="section-heading">
                <div>
                  <h2>{detail.display_name}</h2>
                  <p>{detail.domain}</p>
                </div>
                <div className="heading-actions">
                  <span className="route-label">{detail.dashboard_lab_route}</span>
                  <button
                    type="button"
                    className="copy-button"
                    disabled={refreshing}
                    onClick={() => refreshSelectedProfile()}
                  >
                    {refreshing ? 'Refreshing...' : 'Refresh profile status'}
                  </button>
                </div>
              </div>
              {statusMessage ? <div className="success-banner">{statusMessage}</div> : null}

              <OnboardingOverview detail={detail} />

              <LastActionSummary lastActions={detail.last_actions} />

              <ProviderChecklist detail={detail} />

              <h3>Output Folder Status</h3>
              <ExpectedFilesPanel outputStatus={detail.output_status} />
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Exists</th>
                      <th>JSON</th>
                      <th>Schema</th>
                      <th>Size</th>
                      <th>Last modified</th>
                      <th>Warning</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.output_status.files.map((file) => (
                      <tr key={file.file}>
                        <td>{file.file}</td>
                        <td>{yesNo(file.exists)}</td>
                        <td>{file.json_valid === null ? '' : yesNo(file.json_valid)}</td>
                        <td>{file.schema_version}</td>
                        <td>{file.size}</td>
                        <td>{file.last_modified}</td>
                        <td>{file.warning}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3>Guarded Validation</h3>
              <section className="validation-panel">
                <div>
                  <h4>Validate local output</h4>
                  <p>
                    Reads local metadata only from <code>{detail.paths.local_real_output_folder}</code>.
                    No provider calls, no copy action, no portal action, and no staging/production access.
                  </p>
                </div>
                <label className="confirmation-row">
                  <input
                    type="checkbox"
                    checked={validationConfirmed}
                    onChange={(event) => setValidationConfirmed(event.target.checked)}
                  />
                  <span>
                    I understand this only reads ignored local-real output metadata and does not contact providers or
                    copy files.
                  </span>
                </label>
                <button
                  type="button"
                  className="primary-button"
                  disabled={!validationConfirmed || validationRunning}
                  onClick={() =>
                    runValidation(
                      detail.slug,
                      setValidationRunning,
                      setValidationResult,
                      setError,
                      () => refreshSelectedProfile('Status refreshed after validation'),
                    )
                  }
                >
                  {validationRunning ? 'Validating...' : 'Validate local output'}
                </button>
                {validationResult ? <ValidationResultView validationResult={validationResult} /> : null}
              </section>

              <h3>Guarded Dashboard-Lab Copy</h3>
              <section className="validation-panel">
                <div>
                  <h4>Copy to dashboard-lab local fixtures</h4>
                  <p>
                    Copies only expected JSON fixture files from <code>{copyPreview?.source_folder ?? detail.paths.local_real_output_folder}</code>{' '}
                    into <code>{copyPreview?.destination_folder ?? detail.paths.dashboard_lab_local_fixture_folder}</code>.
                    No provider calls, no portal action, no <code>ga4-snapshot.json</code>, and never committed{' '}
                    <code>public/fixtures</code>.
                  </p>
                </div>
                {copyPreview ? <CopyPreviewView copyPreview={copyPreview} /> : <p>Loading copy preview...</p>}
                <label className="confirmation-row">
                  <input
                    type="checkbox"
                    checked={copyConfirmed}
                    onChange={(event) => setCopyConfirmed(event.target.checked)}
                  />
                  <span>
                    I understand this copies ignored real local output into dashboard-lab public/local-fixtures only and
                    never into committed fixtures.
                  </span>
                </label>
                <button
                  type="button"
                  className="primary-button"
                  disabled={!copyConfirmed || copyRunning || !copyPreview}
                  onClick={() =>
                    runCopy(
                      detail.slug,
                      setCopyRunning,
                      setCopyResult,
                      setError,
                      () => refreshSelectedProfile('Status refreshed after copy'),
                    )
                  }
                >
                  {copyRunning ? 'Copying...' : 'Copy to dashboard-lab local fixtures'}
                </button>
                {copyResult ? <CopyResultView copyResult={copyResult} /> : null}
              </section>

              <h3>Recent Local Actions</h3>
              <section className="history-panel">
                <p>
                  Run history is local-only and reads ignored audit logs. It does not contain provider payloads or
                  secrets.
                </p>
                {actionHistory ? <RunHistoryView history={actionHistory} /> : <p>Loading recent actions...</p>}
              </section>

              <GroupedActionPlan
                actions={detail.action_plan.actions}
                copiedActionId={copiedActionId}
                setCopiedActionId={setCopiedActionId}
              />
            </>
          ) : (
            <div className="empty-state">
              {selectedProfile ? 'Loading selected profile...' : 'No profiles available.'}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

const PROVIDER_ORDER = [
  'ga4',
  'gsc',
  'local_falcon',
  'google_ads_search',
  'callrail',
  'form_fills',
  'profile',
  'dashboard_lab',
];

const STANDARD_PROVIDER_KEYS = ['ga4', 'gsc', 'local_falcon', 'google_ads_search', 'callrail', 'form_fills'];

const PROVIDER_EXPECTED_FILES: Record<string, string> = {
  ga4: 'ga4-summary.json',
  gsc: 'gsc-summary.json',
  local_falcon: 'local-falcon-summary.json',
  google_ads_search: 'google-ads-summary.json',
  callrail: 'callrail-summary.json',
  form_fills: 'form-fills-summary.json',
};

const PROVIDER_SAFETY_NOTES: Record<string, string> = {
  ga4: 'Sanitized GA4 summary output for dashboard-lab; raw snapshot output is not copied to dashboard-lab fixtures.',
  gsc: 'Search Console summary output only; no raw query payloads or OAuth values are shown here.',
  local_falcon: 'Local fixture summary for source-aware visibility where available; API keys and report manifests stay local.',
  google_ads_search: 'Read-only Google Ads Search reporting only; no campaign, budget, bid, keyword, ad, asset, conversion, or account mutations.',
  callrail: 'Aggregate CallRail summary only; no caller names, phone numbers, recordings, transcripts, or raw rows.',
  form_fills: 'Date-only conversion counts; names, emails, phone numbers, messages, IPs, and form payloads are not allowed.',
  profile: 'Validates local-real output metadata without returning raw fixture payloads.',
  dashboard_lab: 'Guarded copy targets dashboard-lab public/local-fixtures only and excludes ga4-snapshot.json.',
};

function OnboardingOverview({ detail }: { detail: ProfileDetail }) {
  const providerCount = detail.provider_setup_checklist.length || detail.provider_readiness.length;
  const outputCount = detail.output_status.files.filter((file) => file.exists).length;
  const expectedCount = detail.output_status.expected_files.length || detail.output_status.files.length;
  const enabledProviders = detail.enabled_providers.map(providerLabel).join(', ');

  return (
    <section className="onboarding-panel" aria-label="Profile onboarding overview">
      <div className="checklist-heading">
        <div>
          <h3>Onboarding Checklist</h3>
          <p>
            Read left to right: profile basics, ignored local config, credentials or local inputs, provider outputs,
            validation, then guarded dashboard-lab copy.
          </p>
        </div>
        <span className="badge neutral">{providerCount} provider steps</span>
      </div>
      <div className="phase-strip" aria-label="Onboarding phases">
        <PhaseStep title="1. Profile basics" detail={`${detail.vertical} · ${detail.service_model}`} ready />
        <PhaseStep title="2. Local config" detail="Ignored local env/config only" ready={detail.safety.local_only} />
        <PhaseStep title="3. Credentials or inputs" detail="Presence checks only" ready />
        <PhaseStep title="4. Provider outputs" detail={`${outputCount} of ${expectedCount} files exist`} ready={detail.output_status.ok} />
        <PhaseStep title="5. Validation" detail="Reads local-real metadata" ready={Boolean(detail.last_actions.last_validation)} />
        <PhaseStep title="6. Guarded copy" detail="Allowlisted summaries only" ready={Boolean(detail.last_actions.last_copy)} />
      </div>
      <dl className="profile-grid">
        <div>
          <dt>Enabled providers</dt>
          <dd>{enabledProviders || 'No provider sources enabled'}</dd>
        </div>
        <div>
          <dt>Dashboard-lab route</dt>
          <dd>{detail.dashboard_lab_route}</dd>
        </div>
        <div>
          <dt>Local-real output</dt>
          <dd>{detail.paths.local_real_output_folder}</dd>
        </div>
        <div>
          <dt>Dashboard-lab local fixture</dt>
          <dd>{detail.paths.dashboard_lab_local_fixture_folder}</dd>
        </div>
      </dl>
    </section>
  );
}

function PhaseStep({ title, detail, ready }: { title: string; detail: string; ready: boolean }) {
  return (
    <article className={ready ? 'phase-step ready' : 'phase-step'}>
      <strong>{title}</strong>
      <span>{detail}</span>
    </article>
  );
}

function ProviderChecklist({ detail }: { detail: ProfileDetail }) {
  const providerReadiness = new Map(detail.provider_readiness.map((provider) => [provider.provider, provider]));
  const sourceChecklist = detail.provider_setup_checklist.length
    ? detail.provider_setup_checklist
    : detail.provider_readiness.map(readinessToChecklistItem);
  const seenProviders = new Set(sourceChecklist.map((item) => item.provider_key));
  const catalogFallbacks = STANDARD_PROVIDER_KEYS.filter((provider) => !seenProviders.has(provider)).map((provider) =>
    disabledProviderChecklistItem(provider),
  );
  const checklist = [...sourceChecklist, ...catalogFallbacks];
  const sortedChecklist = [...checklist].sort(
    (a, b) => providerSortIndex(a.provider_key) - providerSortIndex(b.provider_key),
  );

  return (
    <section className="provider-checklist" aria-label="Provider onboarding checklist">
      <div className="checklist-heading">
        <div>
          <h3>Provider Checklist</h3>
          <p>
            Each card shows readiness without exposing secret values, customer IDs, raw local config, or provider rows.
          </p>
        </div>
      </div>
      <div className="provider-grid">
        {sortedChecklist.map((item) => (
          <ProviderChecklistCard
            key={item.provider_key}
            item={item}
            readiness={providerReadiness.get(item.provider_key)}
          />
        ))}
      </div>
    </section>
  );
}

function ProviderChecklistCard({
  item,
  readiness,
}: {
  item: ProviderSetupChecklistItem;
  readiness: ProviderReadiness | undefined;
}) {
  const configItems = Object.entries(item.config_state);
  const configReady = readiness?.config_ready ?? (item.status === 'ready' || item.status === 'output_available');
  const outputReady = readiness?.output_file_exists ?? item.output_exists;

  return (
    <article className="provider-card">
      <div className="card-heading">
        <div>
          <h4>{item.provider_label}</h4>
          <p>{PROVIDER_SAFETY_NOTES[item.provider_key] ?? 'Local dashboard summary output only.'}</p>
        </div>
        <span className={checklistStatusClass(item.status, item.severity)}>{checklistStatusLabel(item.status)}</span>
      </div>

      <div className="readiness-rail" aria-label={`${item.provider_label} readiness`}>
        <ReadinessPip label="Config" ready={configReady || item.local_config_file_present} />
        <ReadinessPip label="Credentials / input" ready={readiness?.credentials_ready ?? configReady} />
        <ReadinessPip label="Output" ready={outputReady} />
        <ReadinessPip label="Validate" ready={item.validate_readiness === 'Ready'} />
        <ReadinessPip label="Copy" ready={item.dashboard_copy_readiness === 'Ready'} />
      </div>

      <dl className="provider-meta">
        <div>
          <dt>Expected summary</dt>
          <dd>{item.expected_output_file || readiness?.expected_output_file || 'No provider summary expected'}</dd>
        </div>
        <div>
          <dt>Local output</dt>
          <dd>{item.local_output_state || (outputReady ? 'Output exists' : 'Missing')}</dd>
        </div>
        <div>
          <dt>Dashboard writer</dt>
          <dd>{item.dashboard_lab_writer_status || 'Not reported'}</dd>
        </div>
        <div>
          <dt>Copy readiness</dt>
          <dd>{item.dashboard_copy_readiness || 'Not reported'}</dd>
        </div>
      </dl>

      {item.required_config_items.length ? (
        <div className="mini-section">
          <h5>Setup needs</h5>
          <div className="chip-row">
            {item.required_config_items.map((requiredItem) => (
              <span className="setup-chip" key={requiredItem}>
                {requiredItem}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {configItems.length && item.config_visible ? (
        <div className="mini-section">
          <h5>Local readiness checks</h5>
          <ul className="status-list">
            {configItems.map(([key, value]) => (
              <li key={key}>
                <span className={value ? 'tiny-dot ok' : 'tiny-dot warn'} />
                <span>{humanizeKey(key)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {item.missing_config_details.length ? (
        <div className="mini-section">
          <h5>Missing</h5>
          <ul>
            {item.missing_config_details.map((missing) => (
              <li key={missing}>{missing}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className={item.blocked_reason ? 'blocked-reason' : 'next-action'}>
        <strong>{item.blocked_reason ? 'Blocked: ' : 'Next: '}</strong>
        {item.blocked_reason || item.safe_next_action}
      </p>
    </article>
  );
}

function ExpectedFilesPanel({ outputStatus }: { outputStatus: OutputStatus }) {
  const expectedFiles = mergeExpectedFiles(
    outputStatus.expected_files.length ? outputStatus.expected_files : outputStatus.files.map((file) => file.file),
  );
  return (
    <section className="expected-files-panel" aria-label="Expected dashboard-lab summary files">
      <div>
        <h4>Expected dashboard-lab summaries</h4>
        <p>
          Guarded copy uses this allowlist of dashboard summary files. <code>ga4-snapshot.json</code> is intentionally
          excluded from dashboard-lab fixture copy.
        </p>
      </div>
      <div className="file-chip-row">
        {expectedFiles.map((file) => (
          <span className={file === 'ga4-snapshot.json' ? 'file-chip excluded' : 'file-chip'} key={file}>
            {file}
          </span>
        ))}
      </div>
    </section>
  );
}

function GroupedActionPlan({
  actions,
  copiedActionId,
  setCopiedActionId,
}: {
  actions: ActionPlanItem[];
  copiedActionId: string;
  setCopiedActionId: (actionId: string) => void;
}) {
  const groups = groupActionsByProvider(actions);
  return (
    <section className="action-plan-panel" aria-label="Grouped action plan">
      <div className="checklist-heading">
        <div>
          <h3>Provider Action Plan</h3>
          <p>
            Commands are copyable guidance for operator-run local workflows. The console only exposes guarded validation
            and dashboard-lab copy actions.
          </p>
        </div>
      </div>
      <div className="action-group-stack">
        {groups.map(([provider, providerActions]) => (
          <section className="action-group" key={provider} aria-label={`${providerLabel(provider)} action plan`}>
            <div className="action-group-heading">
              <div>
                <h4>{providerLabel(provider)}</h4>
                <p>{PROVIDER_SAFETY_NOTES[provider] ?? 'Local workflow guidance only.'}</p>
              </div>
            </div>
            <div className="action-grid">
              {providerActions.map((action) => (
                <ActionCard
                  action={action}
                  copiedActionId={copiedActionId}
                  setCopiedActionId={setCopiedActionId}
                  key={action.id}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function ActionCard({
  action,
  copiedActionId,
  setCopiedActionId,
}: {
  action: ActionPlanItem;
  copiedActionId: string;
  setCopiedActionId: (actionId: string) => void;
}) {
  return (
    <article className="action-card">
      <div className="card-heading">
        <div>
          <h4>{action.label}</h4>
          <p>{providerLabel(action.provider)}</p>
        </div>
        <span className={statusClass(action.status)}>{statusLabel(action.status)}</span>
      </div>

      {action.blocked_reason ? (
        <p className="blocked-reason">
          <strong>Blocked:</strong> {action.blocked_reason}
        </p>
      ) : null}

      {action.missing_inputs.length ? (
        <div className="mini-section">
          <h5>Missing Inputs</h5>
          <ul>
            {action.missing_inputs.map((input) => (
              <li key={input}>{input}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <dl className="action-meta">
        <div>
          <dt>Expected output</dt>
          <dd>{action.expected_output}</dd>
        </div>
        <div>
          <dt>Manual step</dt>
          <dd>{action.manual_step}</dd>
        </div>
      </dl>

      {action.command ? (
        <div className="command-block">
          <div className="command-heading">
            <span>Copyable operator command</span>
            <button
              type="button"
              className="copy-button"
              onClick={() => copyCommand(action.id, action.command, setCopiedActionId)}
            >
              {copiedActionId === action.id ? 'Copied' : 'Copy command'}
            </button>
          </div>
          <pre>{action.command}</pre>
        </div>
      ) : null}

      <div className="mini-section">
        <h5>Safety Notes</h5>
        <ul>
          {action.safety_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </div>
    </article>
  );
}

function ReadinessPip({ label, ready }: { label: string; ready: boolean }) {
  return (
    <span className={ready ? 'readiness-pip ok' : 'readiness-pip warn'}>
      <span aria-hidden="true" />
      {label}
    </span>
  );
}

function readinessToChecklistItem(provider: ProviderReadiness): ProviderSetupChecklistItem {
  return {
    provider_key: provider.provider,
    provider_label: provider.label,
    expected_output_file: provider.expected_output_file,
    output_exists: provider.output_file_exists,
    local_output_state: provider.output_file_exists ? 'Output exists' : 'Missing output',
    dashboard_lab_writer_status: 'Available',
    required_config_items: [],
    local_config_file_present: provider.readiness.config_present,
    local_config_path_label: '',
    local_config_valid: true,
    local_config_error: '',
    config_state: {
      config_present: provider.readiness.config_present,
      credentials_present: provider.readiness.credentials_present,
    },
    config_visible: true,
    missing_config_details: provider.config_ready ? [] : ['Local config or credentials need attention'],
    safe_next_action: provider.output_file_exists ? 'Validate existing output or copy when ready.' : 'Create local output, then validate.',
    blocked_reason: provider.config_ready ? '' : 'Local provider config is not complete.',
    status: provider.config_ready ? 'ready' : 'needs_config',
    severity: provider.config_ready ? 'ok' : 'warning',
    capability_status: provider.enabled ? 'enabled' : 'planned',
    supported_in_console: true,
    validation_ready: provider.output_file_exists ? 'Ready' : 'Not available yet',
    dashboard_copy_ready: provider.output_file_exists ? 'Ready' : 'Not available yet',
    validate_readiness: provider.output_file_exists ? 'Ready' : 'Not available yet',
    dashboard_copy_readiness: provider.output_file_exists ? 'Ready' : 'Not available yet',
  };
}

function disabledProviderChecklistItem(provider: string): ProviderSetupChecklistItem {
  return {
    provider_key: provider,
    provider_label: providerLabel(provider),
    expected_output_file: PROVIDER_EXPECTED_FILES[provider] ?? '',
    output_exists: false,
    local_output_state: 'Not enabled for this profile',
    dashboard_lab_writer_status: 'Available when enabled',
    required_config_items: [],
    local_config_file_present: false,
    local_config_path_label: '',
    local_config_valid: true,
    local_config_error: '',
    config_state: {},
    config_visible: false,
    missing_config_details: [],
    safe_next_action: 'Enable this provider in the profile registry before preparing local output.',
    blocked_reason: 'Provider is not enabled for this profile.',
    status: 'not_enabled',
    severity: 'neutral',
    capability_status: 'planned',
    supported_in_console: true,
    validation_ready: 'Not available yet',
    dashboard_copy_ready: 'Not available yet',
    validate_readiness: 'Not available yet',
    dashboard_copy_readiness: 'Not available yet',
  };
}

function groupActionsByProvider(actions: ActionPlanItem[]) {
  const grouped = new Map<string, ActionPlanItem[]>();
  for (const action of actions) {
    const current = grouped.get(action.provider) ?? [];
    current.push(action);
    grouped.set(action.provider, current);
  }
  return [...grouped.entries()].sort(([a], [b]) => providerSortIndex(a) - providerSortIndex(b));
}

function providerSortIndex(provider: string) {
  const index = PROVIDER_ORDER.indexOf(provider);
  return index === -1 ? PROVIDER_ORDER.length : index;
}

function mergeExpectedFiles(files: string[]) {
  const merged = [
    'client-profile.json',
    'combined-dashboard-summary.json',
    ...files,
  ];
  return [...new Set(merged)].filter((file) => file !== 'ga4-snapshot.json');
}

function checklistStatusLabel(status: string) {
  const labels: Record<string, string> = {
    ready: 'Ready',
    output_available: 'Output exists',
    ready_to_fetch: 'Ready for local run',
    needs_config: 'Needs config',
    not_enabled: 'Not enabled',
    planned: 'Planned',
    capability: 'Capability',
  };
  return labels[status] ?? statusLabel(status);
}

function checklistStatusClass(status: string, severity: string) {
  if (status === 'ready' || status === 'output_available' || severity === 'ok') {
    return 'badge ok';
  }
  if (status === 'ready_to_fetch' || status === 'planned' || status === 'capability' || status === 'not_enabled') {
    return 'badge neutral';
  }
  return 'badge warn';
}

function humanizeKey(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function yesNo(value: boolean) {
  return value ? 'Yes' : 'No';
}

function refreshProfileStatus(
  slug: string,
  setDetail: (detail: ProfileDetail) => void,
  setCopyPreview: (copyPreview: CopyPreview) => void,
  setActionHistory: (history: ActionRunHistory) => void,
  setError: (error: string) => void,
  setRefreshing: (refreshing: boolean) => void,
  setStatusMessage: (message: string) => void,
  successMessage = '',
) {
  setRefreshing(true);
  Promise.all([
    fetchJson<ProfileDetail>(`${API_BASE}/api/profiles/${slug}`),
    fetchJson<CopyPreview>(`${API_BASE}/api/profiles/${slug}/actions/copy-to-dashboard-lab/preview`),
    fetchJson<ActionRunHistory>(`${API_BASE}/api/profiles/${slug}/action-runs?limit=10`),
  ])
    .then(([profileDetail, copyPreview, actionHistory]) => {
      setDetail(profileDetail);
      setCopyPreview(copyPreview);
      setActionHistory(actionHistory);
      setError('');
      setStatusMessage(successMessage);
    })
    .catch((fetchError: Error) => setError(fetchError.message))
    .finally(() => setRefreshing(false));
}

function fetchJson<T>(url: string): Promise<T> {
  return fetch(url).then((response) => {
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }
    return response.json() as Promise<T>;
  });
}

function LastActionSummary({ lastActions }: { lastActions: LastActions }) {
  return (
    <div className="summary-grid">
      <ActionSummaryCard title="Last action" entry={lastActions.last_action} />
      <ActionSummaryCard title="Last validation" entry={lastActions.last_validation} />
      <ActionSummaryCard title="Last copy" entry={lastActions.last_copy} />
    </div>
  );
}

function ActionSummaryCard({ title, entry }: { title: string; entry: ActionRunEntry | null }) {
  return (
    <article className="summary-card">
      <h4>{title}</h4>
      {entry ? (
        <>
          <strong>{actionLabel(entry.action_id)}</strong>
          <span>{entry.status}</span>
          <span>{entry.timestamp}</span>
        </>
      ) : (
        <span>No local action recorded</span>
      )}
    </article>
  );
}

function statusLabel(status: string) {
  if (status === 'ready') {
    return 'Ready to run locally';
  }
  if (status === 'manual_only') {
    return 'Manual step';
  }
  if (status.startsWith('blocked')) {
    return 'Blocked';
  }
  return status;
}

function statusClass(status: string) {
  if (status === 'ready') {
    return 'badge ok';
  }
  if (status === 'manual_only') {
    return 'badge neutral';
  }
  return 'badge warn';
}

function providerLabel(provider: string) {
  const labels: Record<string, string> = {
    ga4: 'GA4',
    gsc: 'GSC',
    local_falcon: 'Local Falcon',
    google_ads_search: 'Google Ads Search',
    callrail: 'CallRail',
    form_fills: 'Form Fills',
    profile: 'Profile Output',
    dashboard_lab: 'Dashboard Lab',
  };
  return labels[provider] ?? provider;
}

function actionLabel(actionId: string) {
  const labels: Record<string, string> = {
    'validate-output': 'Validate output',
    'copy-to-dashboard-lab': 'Copy to dashboard-lab',
    'ga4-snapshot': 'GA4 summary workflow',
    'gsc-fetch': 'GSC local-real fetch',
    'local-falcon-read-only-fetch': 'Local Falcon read-only fetch',
    'google-ads-search-read-only-export': 'Google Ads Search read-only export',
    'callrail-csv-import': 'CallRail CSV import',
    'form-fills-date-only-import': 'Form Fills date-only import',
  };
  return labels[actionId] ?? actionId;
}

function copyCommand(
  actionId: string,
  command: string,
  setCopiedActionId: (actionId: string) => void,
) {
  void navigator.clipboard.writeText(command).then(() => {
    setCopiedActionId(actionId);
    window.setTimeout(() => setCopiedActionId(''), 1600);
  });
}

function runValidation(
  slug: string,
  setValidationRunning: (running: boolean) => void,
  setValidationResult: (result: ValidationRunResult | null) => void,
  setError: (error: string) => void,
  onComplete: () => void,
) {
  setValidationRunning(true);
  fetch(`${API_BASE}/api/profiles/${slug}/actions/validate-output`, {
    method: 'POST',
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json();
    })
    .then((payload: ValidationRunResult) => {
      setValidationResult(payload);
      setError('');
      onComplete();
    })
    .catch((fetchError: Error) => setError(fetchError.message))
    .finally(() => setValidationRunning(false));
}

function ValidationResultView({ validationResult }: { validationResult: ValidationRunResult }) {
  return (
    <div className="validation-result">
      <div className="result-summary">
        <span className={validationStatusClass(validationResult.status)}>
          {validationStatusLabel(validationResult.status)}
        </span>
        <span>{validationResult.duration_ms} ms</span>
        <span>Audit log: {validationResult.audit.logged ? 'written' : 'not written'}</span>
      </div>
      {validationResult.result.warnings.length ? (
        <div className="mini-section">
          <h5>Warnings</h5>
          <ul>
            {validationResult.result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Required</th>
              <th>Exists</th>
              <th>JSON</th>
              <th>Schema</th>
              <th>Size</th>
              <th>Warning</th>
            </tr>
          </thead>
          <tbody>
            {validationResult.result.files.map((file) => (
              <tr key={file.file}>
                <td>{file.file}</td>
                <td>{yesNo(file.required)}</td>
                <td>{yesNo(file.exists)}</td>
                <td>{file.json_valid === null ? '' : yesNo(file.json_valid)}</td>
                <td>{file.schema_version}</td>
                <td>{file.size}</td>
                <td>{file.warning}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mini-section">
        <h5>Guardrails</h5>
        <ul>
          {validationResult.guardrails.map((guardrail) => (
            <li key={guardrail}>{guardrail}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function RunHistoryView({ history }: { history: ActionRunHistory }) {
  if (!history.entries.length) {
    return <div className="empty-state compact-empty">No local actions recorded for this profile.</div>;
  }
  return (
    <>
      {history.skipped_malformed ? (
        <p className="blocked-reason">Skipped malformed audit line(s): {history.skipped_malformed}</p>
      ) : null}
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Action</th>
              <th>Status</th>
              <th>Summary</th>
              <th>Warnings</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            {history.entries.map((entry) => (
              <tr key={entry.audit_entry_id}>
                <td>{entry.timestamp}</td>
                <td>{actionLabel(entry.action_id)}</td>
                <td>{entry.status}</td>
                <td>{runSummary(entry)}</td>
                <td>{entry.warnings_count}</td>
                <td>{entry.duration_ms === null ? '' : `${entry.duration_ms} ms`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function runSummary(entry: ActionRunEntry) {
  if (entry.action_id === 'copy-to-dashboard-lab') {
    return `copied ${entry.file_counts.copied ?? 0}, overwritten ${entry.file_counts.overwritten ?? 0}, skipped ${entry.file_counts.skipped ?? 0}, failed ${entry.file_counts.failed ?? 0}`;
  }
  if (entry.action_id === 'validate-output') {
    return `missing ${entry.result_summary.missing_required_file_count ?? 0}, invalid ${entry.result_summary.malformed_json_file_count ?? 0}`;
  }
  return '';
}

function CopyPreviewView({ copyPreview }: { copyPreview: CopyPreview }) {
  return (
    <div className="validation-result">
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Source</th>
              <th>Destination</th>
              <th>Source exists</th>
              <th>Destination exists</th>
              <th>Action</th>
              <th>Size</th>
              <th>Last modified</th>
            </tr>
          </thead>
          <tbody>
            {copyPreview.items.map((item) => (
              <tr key={item.file}>
                <td>{item.file}</td>
                <td>{item.source}</td>
                <td>{item.destination}</td>
                <td>{yesNo(item.source_exists)}</td>
                <td>{yesNo(item.destination_exists)}</td>
                <td>{copyActionLabel(item.action)}</td>
                <td>{item.size}</td>
                <td>{item.last_modified}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mini-section">
        <h5>Guardrails</h5>
        <ul>
          {copyPreview.guardrails.map((guardrail) => (
            <li key={guardrail}>{guardrail}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function CopyResultView({ copyResult }: { copyResult: CopyRunResult }) {
  return (
    <div className="validation-result">
      <div className="result-summary">
        <span className={copyResult.status === 'ok' ? 'badge ok' : 'badge warn'}>
          {copyResult.status === 'ok' ? 'Copy complete' : 'Copy completed with failures'}
        </span>
        <span>{copyResult.duration_ms} ms</span>
        <span>Audit log: {copyResult.audit.logged ? 'written' : 'not written'}</span>
        <span>
          copied {copyResult.counts.copied}, overwritten {copyResult.counts.overwritten}, skipped{' '}
          {copyResult.counts.skipped_missing_source}, failed {copyResult.counts.failed}
        </span>
      </div>
      {copyResult.warnings.length ? (
        <div className="mini-section">
          <h5>Warnings</h5>
          <ul>
            {copyResult.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Status</th>
              <th>Source</th>
              <th>Destination</th>
              <th>Size</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {copyResult.items.map((item) => (
              <tr key={item.file}>
                <td>{item.file}</td>
                <td>{copyStatusLabel(item.status)}</td>
                <td>{item.source}</td>
                <td>{item.destination}</td>
                <td>{item.size}</td>
                <td>{item.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function runCopy(
  slug: string,
  setCopyRunning: (running: boolean) => void,
  setCopyResult: (result: CopyRunResult | null) => void,
  setError: (error: string) => void,
  onComplete: () => void,
) {
  setCopyRunning(true);
  fetch(`${API_BASE}/api/profiles/${slug}/actions/copy-to-dashboard-lab`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed: true }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json();
    })
    .then((payload: CopyRunResult) => {
      setCopyResult(payload);
      setError('');
      onComplete();
    })
    .catch((fetchError: Error) => setError(fetchError.message))
    .finally(() => setCopyRunning(false));
}

function copyActionLabel(action: string) {
  const labels: Record<string, string> = {
    copy: 'Copy',
    overwrite: 'Overwrite',
    skip_missing_source: 'Skip missing source',
  };
  return labels[action] ?? action;
}

function copyStatusLabel(status: string) {
  const labels: Record<string, string> = {
    copied: 'Copied',
    overwritten: 'Overwritten',
    skipped_missing_source: 'Skipped missing source',
    failed: 'Failed',
  };
  return labels[status] ?? status;
}

function validationStatusLabel(status: string) {
  const labels: Record<string, string> = {
    ok: 'OK',
    warning: 'Warning',
    missing_outputs: 'Missing outputs',
    invalid_json: 'Invalid JSON',
    folder_missing: 'Folder missing',
  };
  return labels[status] ?? status;
}

function validationStatusClass(status: string) {
  if (status === 'ok') {
    return 'badge ok';
  }
  if (status === 'warning') {
    return 'badge neutral';
  }
  return 'badge warn';
}

export default App;
