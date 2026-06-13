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

type SecretVaultStatus = {
  exists: boolean;
  unlocked: boolean;
  status: string;
  error: string;
  entries: unknown[];
  entry_count: number;
};

type SecretMetadata = {
  configured: boolean;
  profile: string;
  provider: string;
  key: string;
  classification: string;
  source: string;
  created_at: string;
  updated_at: string;
  value_returned: boolean;
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
  const [vaultStatus, setVaultStatus] = useState<SecretVaultStatus | null>(null);
  const [vaultPassphrase, setVaultPassphrase] = useState<string>('');
  const [vaultBusy, setVaultBusy] = useState<boolean>(false);
  const [vaultMessage, setVaultMessage] = useState<string>('');
  const [localFalconSecretStatus, setLocalFalconSecretStatus] = useState<SecretMetadata | null>(null);
  const [localFalconApiKey, setLocalFalconApiKey] = useState<string>('');
  const [localFalconSecretBusy, setLocalFalconSecretBusy] = useState<boolean>(false);
  const [localFalconSecretMessage, setLocalFalconSecretMessage] = useState<string>('');
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
    refreshVaultStatus(setVaultStatus, setVaultMessage, setVaultBusy);
  }, []);

  useEffect(() => {
    setLocalFalconApiKey('');
    setLocalFalconSecretMessage('');
    if (!selectedSlug || !vaultStatus?.unlocked) {
      setLocalFalconSecretStatus(null);
      return;
    }
    refreshProfileSecrets(
      selectedSlug,
      setLocalFalconSecretStatus,
      setLocalFalconSecretMessage,
      setLocalFalconSecretBusy,
    );
  }, [selectedSlug, vaultStatus?.unlocked]);

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

              <SimpleOnboardingSummary detail={detail} copyPreview={copyPreview} />

              <SecretVaultPanel
                passphrase={vaultPassphrase}
                setPassphrase={setVaultPassphrase}
                status={vaultStatus}
                profileSlug={detail.slug}
                message={vaultMessage}
                busy={vaultBusy}
                localFalconStatus={localFalconSecretStatus}
                localFalconApiKey={localFalconApiKey}
                localFalconBusy={localFalconSecretBusy}
                localFalconMessage={localFalconSecretMessage}
                setLocalFalconApiKey={setLocalFalconApiKey}
                onRefresh={() => refreshVaultStatus(setVaultStatus, setVaultMessage, setVaultBusy, 'Vault status refreshed')}
                onUnlock={(createIfMissing) =>
                  unlockVault(
                    vaultPassphrase,
                    createIfMissing,
                    setVaultStatus,
                    setVaultMessage,
                    setVaultBusy,
                    setVaultPassphrase,
                  )
                }
                onLock={() => lockVault(setVaultStatus, setVaultMessage, setVaultBusy)}
                onSaveLocalFalconKey={() =>
                  saveLocalFalconApiKey(
                    detail.slug,
                    localFalconApiKey,
                    setLocalFalconSecretStatus,
                    setLocalFalconSecretMessage,
                    setLocalFalconSecretBusy,
                    setLocalFalconApiKey,
                    () => refreshVaultStatus(setVaultStatus, setVaultMessage, setVaultBusy),
                  )
                }
                onDeleteLocalFalconKey={() =>
                  deleteLocalFalconApiKey(
                    detail.slug,
                    setLocalFalconSecretStatus,
                    setLocalFalconSecretMessage,
                    setLocalFalconSecretBusy,
                    () => refreshVaultStatus(setVaultStatus, setVaultMessage, setVaultBusy),
                  )
                }
              />

              <PrimaryNextAction detail={detail} copyPreview={copyPreview} />

              <ProviderChecklist detail={detail} />

              <SafeCopyReadiness
                detail={detail}
                copyPreview={copyPreview}
                validationConfirmed={validationConfirmed}
                setValidationConfirmed={setValidationConfirmed}
                validationRunning={validationRunning}
                validationResult={validationResult}
                copyConfirmed={copyConfirmed}
                setCopyConfirmed={setCopyConfirmed}
                copyRunning={copyRunning}
                copyResult={copyResult}
                onValidate={() =>
                  runValidation(
                    detail.slug,
                    setValidationRunning,
                    setValidationResult,
                    setError,
                    () => refreshSelectedProfile('Status refreshed after validation'),
                  )
                }
                onCopy={() =>
                  runCopy(
                    detail.slug,
                    setCopyRunning,
                    setCopyResult,
                    setError,
                    () => refreshSelectedProfile('Status refreshed after copy'),
                  )
                }
              />

              <details className="advanced-panel">
                <summary>Advanced / Operator Diagnostics</summary>
                <div className="advanced-content">
                  <LastActionSummary lastActions={detail.last_actions} />

                  <h3>Expected Dashboard Files</h3>
                  <ExpectedFilesPanel outputStatus={detail.output_status} />

                  <h3>Output Folder Details</h3>
                  <OutputStatusTable outputStatus={detail.output_status} />

                  {validationResult ? (
                    <>
                      <h3>Validation Details</h3>
                      <ValidationResultView validationResult={validationResult} />
                    </>
                  ) : null}

                  {copyPreview ? (
                    <>
                      <h3>Copy Preview Details</h3>
                      <CopyPreviewView copyPreview={copyPreview} />
                    </>
                  ) : null}

                  {copyResult ? (
                    <>
                      <h3>Copy Result Details</h3>
                      <CopyResultView copyResult={copyResult} />
                    </>
                  ) : null}

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
                </div>
              </details>
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

function SimpleOnboardingSummary({
  detail,
  copyPreview,
}: {
  detail: ProfileDetail;
  copyPreview: CopyPreview | null;
}) {
  const summary = onboardingSummary(detail, copyPreview);
  return (
    <section className="simple-summary-card" aria-label="Client onboarding summary">
      <div className="simple-summary-main">
        <div>
          <span className="eyebrow">Client onboarding</span>
          <h3>{detail.display_name}</h3>
          <p>{detail.slug}</p>
        </div>
        <span className={summary.statusClass}>{summary.status}</span>
      </div>
      <p className="next-step-copy">{summary.nextStep}</p>
      <div className="summary-counts" aria-label="Onboarding status counts">
        <MetricPill label="Enabled providers" value={summary.enabledProviders} />
        <MetricPill label="Ready providers" value={summary.readyProviders} />
        <MetricPill label="Missing outputs" value={summary.missingOutputs} />
        <MetricPill label="Validation" value={summary.validationStatus} />
        <MetricPill label="Copy readiness" value={summary.copyStatus} />
      </div>
    </section>
  );
}

function MetricPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SecretVaultPanel({
  status,
  profileSlug,
  passphrase,
  setPassphrase,
  message,
  busy,
  localFalconStatus,
  localFalconApiKey,
  localFalconBusy,
  localFalconMessage,
  setLocalFalconApiKey,
  onRefresh,
  onUnlock,
  onLock,
  onSaveLocalFalconKey,
  onDeleteLocalFalconKey,
}: {
  status: SecretVaultStatus | null;
  profileSlug: string;
  passphrase: string;
  setPassphrase: (value: string) => void;
  message: string;
  busy: boolean;
  localFalconStatus: SecretMetadata | null;
  localFalconApiKey: string;
  localFalconBusy: boolean;
  localFalconMessage: string;
  setLocalFalconApiKey: (value: string) => void;
  onRefresh: () => void;
  onUnlock: (createIfMissing: boolean) => void;
  onLock: () => void;
  onSaveLocalFalconKey: () => void;
  onDeleteLocalFalconKey: () => void;
}) {
  const vaultExists = status?.exists === true;
  const isUnlocked = status?.unlocked === true;
  const isMissing = status?.exists === false;
  const hasPassphrase = passphrase.trim().length > 0;
  const statusText = status ? (isUnlocked ? 'Unlocked' : 'Locked') : 'Unknown';
  const existsText = status ? (vaultExists ? 'Exists' : 'Missing') : 'Checking';
  const entryCount = status?.entry_count ?? 0;
  const safeMessage = message || (status?.status === 'error' ? 'Vault status needs attention.' : '');

  return (
    <section className="secret-vault-card" aria-label="Secret Vault status">
      <div className="secret-vault-heading">
        <div>
          <span className="eyebrow">Security settings</span>
          <h3>Secret Vault</h3>
          <p>
            Unlocks the local encrypted vault for this backend session only. This panel does not run provider imports,
            store new secrets, or copy fixtures.
          </p>
        </div>
        <span className={isUnlocked ? 'badge ok' : vaultExists ? 'badge neutral' : 'badge warn'}>
          {statusText}
        </span>
      </div>

      <div className="vault-status-grid" aria-label="Vault safe status">
        <MetricPill label="Vault file" value={existsText} />
        <MetricPill label="Session" value={statusText} />
        <MetricPill label="Entries" value={entryCount} />
      </div>

      {safeMessage ? <p className="vault-message">{safeMessage}</p> : null}

      <div className="vault-controls">
        <label className="vault-passphrase-field">
          <span>Passphrase</span>
          <input
            type="password"
            value={passphrase}
            autoComplete="off"
            onChange={(event) => setPassphrase(event.target.value)}
            placeholder="Enter local vault passphrase"
          />
        </label>
        <div className="vault-button-row">
          <button type="button" className="copy-button" disabled={busy} onClick={onRefresh}>
            Refresh vault status
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={busy || !hasPassphrase || !vaultExists}
            onClick={() => onUnlock(false)}
          >
            Unlock vault
          </button>
          {isMissing ? (
            <button
              type="button"
              className="copy-button"
              disabled={busy || !hasPassphrase}
              onClick={() => onUnlock(true)}
            >
              Create vault and unlock
            </button>
          ) : null}
          <button type="button" className="copy-button" disabled={busy || !isUnlocked} onClick={onLock}>
            Lock vault
          </button>
        </div>
      </div>

      <LocalFalconApiKeyManager
        apiKey={localFalconApiKey}
        busy={localFalconBusy}
        isUnlocked={isUnlocked}
        message={localFalconMessage}
        profileSlug={profileSlug}
        setApiKey={setLocalFalconApiKey}
        status={localFalconStatus}
        onDelete={onDeleteLocalFalconKey}
        onSave={onSaveLocalFalconKey}
      />
    </section>
  );
}

function LocalFalconApiKeyManager({
  apiKey,
  busy,
  isUnlocked,
  message,
  profileSlug,
  setApiKey,
  status,
  onDelete,
  onSave,
}: {
  apiKey: string;
  busy: boolean;
  isUnlocked: boolean;
  message: string;
  profileSlug: string;
  setApiKey: (value: string) => void;
  status: SecretMetadata | null;
  onDelete: () => void;
  onSave: () => void;
}) {
  const [deleteConfirmed, setDeleteConfirmed] = useState<boolean>(false);
  const configured = status?.configured === true;
  const canSave = isUnlocked && apiKey.trim().length > 0 && !busy;

  return (
    <section className="local-secret-manager" aria-label="Local Falcon API key vault management">
      <div className="local-secret-heading">
        <div>
          <h4>Local Falcon API key</h4>
          <p>Saved keys stay encrypted in the local vault. This does not run a Local Falcon pull.</p>
        </div>
        <span className={configured ? 'badge ok' : 'badge warn'}>{configured ? 'Configured' : 'Missing'}</span>
      </div>
      {!isUnlocked ? (
        <p className="vault-message">Unlock the vault to manage Local Falcon API key.</p>
      ) : (
        <>
          <label className="vault-passphrase-field">
            <span>Local Falcon API key</span>
            <input
              type="password"
              value={apiKey}
              autoComplete="off"
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={configured ? 'Enter replacement key' : 'Enter API key'}
            />
          </label>
          <div className="vault-button-row">
            <button type="button" className="primary-button" disabled={!canSave} onClick={onSave}>
              {configured ? 'Replace key' : 'Save key'}
            </button>
            {configured ? (
              <>
                <label className="confirmation-row compact-confirmation local-secret-confirmation">
                  <input
                    type="checkbox"
                    checked={deleteConfirmed}
                    onChange={(event) => setDeleteConfirmed(event.target.checked)}
                  />
                  <span>Confirm deletion of the saved Local Falcon API key.</span>
                </label>
                <button
                  type="button"
                  className="copy-button"
                  disabled={busy || !deleteConfirmed}
                  onClick={() => {
                    onDelete();
                    setDeleteConfirmed(false);
                  }}
                >
                  Delete key
                </button>
              </>
            ) : null}
          </div>
          <p className="safe-copy-footnote">
            Managing this key is scoped to <code>{profileSlug}</code>. The value is write-only and is never shown after saving.
          </p>
        </>
      )}
      {message ? <p className="vault-message">{message}</p> : null}
    </section>
  );
}

function PrimaryNextAction({
  detail,
  copyPreview,
}: {
  detail: ProfileDetail;
  copyPreview: CopyPreview | null;
}) {
  const actions = recommendedNextActions(detail, copyPreview);
  return (
    <section className="next-action-card" aria-label="Recommended next actions">
      <div>
        <span className="eyebrow">Recommended next</span>
        <h3>{actions[0].title}</h3>
        <p>{actions[0].description}</p>
      </div>
      {actions.length > 1 ? (
        <div className="secondary-next-action">
          <strong>{actions[1].title}</strong>
          <span>{actions[1].description}</span>
        </div>
      ) : null}
    </section>
  );
}

function SafeCopyReadiness({
  detail,
  copyPreview,
  validationConfirmed,
  setValidationConfirmed,
  validationRunning,
  validationResult,
  copyConfirmed,
  setCopyConfirmed,
  copyRunning,
  copyResult,
  onValidate,
  onCopy,
}: {
  detail: ProfileDetail;
  copyPreview: CopyPreview | null;
  validationConfirmed: boolean;
  setValidationConfirmed: (confirmed: boolean) => void;
  validationRunning: boolean;
  validationResult: ValidationRunResult | null;
  copyConfirmed: boolean;
  setCopyConfirmed: (confirmed: boolean) => void;
  copyRunning: boolean;
  copyResult: CopyRunResult | null;
  onValidate: () => void;
  onCopy: () => void;
}) {
  const copyReady = Boolean(copyPreview?.items.length) && copyPreview?.items.every((item) => item.source_exists);
  return (
    <section className="safe-copy-card" aria-label="Dashboard-lab copy readiness">
      <div className="safe-copy-heading">
        <div>
          <span className="eyebrow">Guarded finish step</span>
          <h3>Dashboard-lab copy readiness</h3>
          <p>
            Validation checks ignored local-real output. Copy is guarded and moves only allowlisted dashboard summary
            fixtures into <code>public/local-fixtures</code>. <code>ga4-snapshot.json</code> is excluded.
          </p>
        </div>
        <span className={copyReady ? 'badge ok' : 'badge warn'}>{copyReady ? 'Copy sources ready' : 'Copy not ready'}</span>
      </div>

      <div className="guarded-actions">
        <article>
          <h4>Validate local-real outputs</h4>
          <p>No provider calls, no portal access, no fixture copy.</p>
          <label className="confirmation-row compact-confirmation">
            <input
              type="checkbox"
              checked={validationConfirmed}
              onChange={(event) => setValidationConfirmed(event.target.checked)}
            />
            <span>I understand this only reads ignored local output metadata.</span>
          </label>
          <button
            type="button"
            className="primary-button"
            disabled={!validationConfirmed || validationRunning}
            onClick={onValidate}
          >
            {validationRunning ? 'Validating...' : 'Validate local output'}
          </button>
          {validationResult ? (
            <p className="compact-result">
              Result: <strong>{validationStatusLabel(validationResult.status)}</strong>
            </p>
          ) : null}
        </article>

        <article>
          <h4>Copy validated summaries</h4>
          <p>Copies summaries only after explicit confirmation. No raw snapshots or credentials are copied.</p>
          <label className="confirmation-row compact-confirmation">
            <input
              type="checkbox"
              checked={copyConfirmed}
              onChange={(event) => setCopyConfirmed(event.target.checked)}
            />
            <span>I understand this copies ignored summaries into dashboard-lab local fixtures only.</span>
          </label>
          <button
            type="button"
            className="primary-button"
            disabled={!copyConfirmed || copyRunning || !copyPreview}
            onClick={onCopy}
          >
            {copyRunning ? 'Copying...' : 'Copy to dashboard-lab'}
          </button>
          {copyResult ? (
            <p className="compact-result">
              Result: <strong>{copyResult.status === 'ok' ? 'Copy complete' : 'Copy completed with warnings'}</strong>
            </p>
          ) : null}
        </article>
      </div>

      <p className="safe-copy-footnote">
        Output folder: <code>{detail.paths.local_real_output_folder}</code>
      </p>
    </section>
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
  const enabledItems = sortedChecklist.filter((item) => item.status !== 'not_enabled');
  const disabledItems = sortedChecklist.filter((item) => item.status === 'not_enabled');

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
        {enabledItems.map((item) => (
          <ProviderChecklistCard
            key={item.provider_key}
            item={item}
            readiness={providerReadiness.get(item.provider_key)}
          />
        ))}
      </div>
      {disabledItems.length ? (
        <details className="not-enabled-panel">
          <summary>Not enabled for this profile</summary>
          <div className="not-enabled-list">
            {disabledItems.map((item) => (
              <span key={item.provider_key}>{item.provider_label}</span>
            ))}
          </div>
        </details>
      ) : null}
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

function OutputStatusTable({ outputStatus }: { outputStatus: OutputStatus }) {
  return (
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
          {outputStatus.files.map((file) => (
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

function onboardingSummary(detail: ProfileDetail, copyPreview: CopyPreview | null) {
  const enabledItems = activeProviderItems(detail);
  const readyProviders = enabledItems.filter((item) => item.output_exists).length;
  const missingOutputs = enabledItems.filter((item) => !item.output_exists).length;
  const validationStatus = detail.last_actions.last_validation ? 'Done' : detail.output_status.ok ? 'Ready' : 'Needed';
  const copyReady = Boolean(copyPreview?.items.length) && copyPreview?.items.every((item) => item.source_exists);
  const copyStatus = detail.last_actions.last_copy ? 'Copied' : copyReady ? 'Ready' : 'Not ready';
  const firstMissing = enabledItems.find((item) => !item.output_exists);
  const firstBlocked = enabledItems.find((item) => item.blocked_reason);

  let status = 'Needs setup';
  let statusClass = 'badge warn';
  let nextStep = 'Next: review the provider checklist and add the first missing local input or output.';

  if (!enabledItems.length) {
    status = 'Not started';
    nextStep = 'Next: choose a client profile with enabled dashboard providers.';
  } else if (detail.last_actions.last_copy && detail.output_status.ok) {
    status = 'Copied / available locally';
    statusClass = 'badge ok';
    nextStep = 'Next: open dashboard-lab when you want to review the copied local fixture view.';
  } else if (copyReady && detail.output_status.ok) {
    status = 'Ready to copy';
    statusClass = 'badge ok';
    nextStep = 'Next: confirm the guarded copy action when you are ready to update dashboard-lab local fixtures.';
  } else if (detail.output_status.ok) {
    status = 'Ready to validate';
    statusClass = 'badge neutral';
    nextStep = 'Next: validate the local-real output folder, then copy the allowlisted summaries.';
  } else if (readyProviders > 0) {
    status = 'Partially ready';
    statusClass = 'badge neutral';
    nextStep = `Next: ${firstMissing?.safe_next_action || firstBlocked?.blocked_reason || 'finish missing provider output.'}`;
  } else if (firstBlocked) {
    nextStep = `Next: ${firstBlocked.blocked_reason}`;
  }

  return {
    enabledProviders: enabledItems.length,
    readyProviders,
    missingOutputs,
    validationStatus,
    copyStatus,
    status,
    statusClass,
    nextStep,
  };
}

function recommendedNextActions(detail: ProfileDetail, copyPreview: CopyPreview | null) {
  const enabledItems = activeProviderItems(detail);
  const missingConfig = enabledItems.find((item) => item.blocked_reason && !item.output_exists);
  const missingOutput = enabledItems.find((item) => !item.output_exists);
  const copyReady = Boolean(copyPreview?.items.length) && copyPreview?.items.every((item) => item.source_exists);

  if (missingConfig) {
    return [
      {
        title: `Finish ${missingConfig.provider_label} setup`,
        description: missingConfig.blocked_reason || missingConfig.safe_next_action,
      },
    ];
  }
  if (missingOutput) {
    return [
      {
        title: `Create ${missingOutput.provider_label} output`,
        description: missingOutput.safe_next_action,
      },
    ];
  }
  if (!detail.last_actions.last_validation) {
    return [
      {
        title: 'Validate local-real outputs',
        description: 'Run the guarded validation check before copying summaries into dashboard-lab.',
      },
      {
        title: 'Review copy readiness',
        description: 'The copy step remains disabled until you confirm the safety checkbox.',
      },
    ];
  }
  if (copyReady && !detail.last_actions.last_copy) {
    return [
      {
        title: 'Copy summaries to dashboard-lab',
        description: 'Use the guarded copy action to update ignored dashboard-lab local fixtures.',
      },
    ];
  }
  return [
    {
      title: 'Review local dashboard output',
      description: 'The local provider summaries are available. Use advanced diagnostics only when you need commands or file-level detail.',
    },
  ];
}

function activeProviderItems(detail: ProfileDetail) {
  const enabled = new Set(detail.enabled_providers);
  const sourceChecklist = detail.provider_setup_checklist.length
    ? detail.provider_setup_checklist
    : detail.provider_readiness.map(readinessToChecklistItem);
  return sourceChecklist
    .filter((item) => enabled.has(item.provider_key))
    .sort((a, b) => providerSortIndex(a.provider_key) - providerSortIndex(b.provider_key));
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

function refreshVaultStatus(
  setVaultStatus: (status: SecretVaultStatus) => void,
  setVaultMessage: (message: string) => void,
  setVaultBusy: (busy: boolean) => void,
  successMessage = '',
) {
  setVaultBusy(true);
  fetchJson<SecretVaultStatus>(`${API_BASE}/api/secrets/status`)
    .then((payload) => {
      setVaultStatus(payload);
      setVaultMessage(payload.status === 'error' ? 'Vault status could not be read safely.' : successMessage);
    })
    .catch((fetchError: Error) => setVaultMessage(safeVaultErrorMessage(fetchError)))
    .finally(() => setVaultBusy(false));
}

function unlockVault(
  passphrase: string,
  createIfMissing: boolean,
  setVaultStatus: (status: SecretVaultStatus) => void,
  setVaultMessage: (message: string) => void,
  setVaultBusy: (busy: boolean) => void,
  setVaultPassphrase: (value: string) => void,
) {
  if (!passphrase.trim()) {
    setVaultMessage('Enter a local vault passphrase before continuing.');
    return;
  }
  setVaultBusy(true);
  fetch(`${API_BASE}/api/secrets/unlock`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ passphrase, create_if_missing: createIfMissing }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<SecretVaultStatus>;
    })
    .then((payload) => {
      setVaultStatus(payload);
      setVaultPassphrase('');
      setVaultMessage(createIfMissing ? 'Vault created and unlocked for this local session.' : 'Vault unlocked for this local session.');
    })
    .catch((fetchError: Error) => {
      setVaultPassphrase('');
      setVaultMessage(safeVaultErrorMessage(fetchError));
    })
    .finally(() => setVaultBusy(false));
}

function lockVault(
  setVaultStatus: (status: SecretVaultStatus) => void,
  setVaultMessage: (message: string) => void,
  setVaultBusy: (busy: boolean) => void,
) {
  setVaultBusy(true);
  fetch(`${API_BASE}/api/secrets/lock`, {
    method: 'POST',
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<SecretVaultStatus>;
    })
    .then((payload) => {
      setVaultStatus(payload);
      setVaultMessage('Vault locked for this local session.');
    })
    .catch((fetchError: Error) => setVaultMessage(safeVaultErrorMessage(fetchError)))
    .finally(() => setVaultBusy(false));
}

function refreshProfileSecrets(
  profileSlug: string,
  setLocalFalconSecretStatus: (status: SecretMetadata | null) => void,
  setLocalFalconSecretMessage: (message: string) => void,
  setLocalFalconSecretBusy: (busy: boolean) => void,
  successMessage = '',
) {
  setLocalFalconSecretBusy(true);
  fetchJson<{ profile: string; secrets: SecretMetadata[] }>(`${API_BASE}/api/profiles/${profileSlug}/secrets`)
    .then((payload) => {
      setLocalFalconSecretStatus(
        payload.secrets.find((secret) => secret.provider === 'local_falcon' && secret.key === 'api_key') ?? null,
      );
      setLocalFalconSecretMessage(successMessage);
    })
    .catch((fetchError: Error) => setLocalFalconSecretMessage(safeSecretErrorMessage(fetchError)))
    .finally(() => setLocalFalconSecretBusy(false));
}

function saveLocalFalconApiKey(
  profileSlug: string,
  apiKey: string,
  setLocalFalconSecretStatus: (status: SecretMetadata | null) => void,
  setLocalFalconSecretMessage: (message: string) => void,
  setLocalFalconSecretBusy: (busy: boolean) => void,
  setLocalFalconApiKey: (value: string) => void,
  onComplete: () => void,
) {
  if (!apiKey.trim()) {
    setLocalFalconSecretMessage('Enter a Local Falcon API key before saving.');
    return;
  }
  setLocalFalconSecretBusy(true);
  fetch(`${API_BASE}/api/profiles/${profileSlug}/secrets/local_falcon/api_key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: apiKey }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<{ profile: string; secret: SecretMetadata }>;
    })
    .then((payload) => {
      setLocalFalconSecretStatus(payload.secret);
      setLocalFalconSecretMessage('Local Falcon API key saved in the encrypted vault.');
      setLocalFalconApiKey('');
      onComplete();
    })
    .catch((fetchError: Error) => {
      setLocalFalconApiKey('');
      setLocalFalconSecretMessage(safeSecretErrorMessage(fetchError));
    })
    .finally(() => setLocalFalconSecretBusy(false));
}

function deleteLocalFalconApiKey(
  profileSlug: string,
  setLocalFalconSecretStatus: (status: SecretMetadata | null) => void,
  setLocalFalconSecretMessage: (message: string) => void,
  setLocalFalconSecretBusy: (busy: boolean) => void,
  onComplete: () => void,
) {
  setLocalFalconSecretBusy(true);
  fetch(`${API_BASE}/api/profiles/${profileSlug}/secrets/local_falcon/api_key`, {
    method: 'DELETE',
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<{ profile: string; secret: SecretMetadata }>;
    })
    .then((payload) => {
      setLocalFalconSecretStatus(payload.secret);
      setLocalFalconSecretMessage('Local Falcon API key deleted from the encrypted vault.');
      onComplete();
    })
    .catch((fetchError: Error) => setLocalFalconSecretMessage(safeSecretErrorMessage(fetchError)))
    .finally(() => setLocalFalconSecretBusy(false));
}

function safeVaultErrorMessage(error: Error) {
  const status = error.message.match(/\d{3}/)?.[0] ?? '';
  if (status === '401') {
    return 'Vault unlock failed. Check the passphrase and try again.';
  }
  if (status === '400') {
    return 'Vault could not be read safely.';
  }
  if (status === '404') {
    return 'Vault is missing. Create it only when you are ready to initialize a local vault.';
  }
  return status ? `Vault request failed with status ${status}.` : 'Vault request failed.';
}

function safeSecretErrorMessage(error: Error) {
  const status = error.message.match(/\d{3}/)?.[0] ?? '';
  if (status === '423') {
    return 'Unlock the vault to manage Local Falcon API key.';
  }
  if (status === '400') {
    return 'Local Falcon API key could not be saved safely.';
  }
  if (status === '404') {
    return 'Profile or secret setting was not found.';
  }
  return status ? `Secret request failed with status ${status}.` : 'Secret request failed.';
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
