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

type LocalConfigField = {
  provider: string;
  key: string;
  label: string;
  kind: string;
  required: boolean;
  secret_value_allowed: boolean;
};

type LocalConfigDraft = {
  profile: string;
  ga4: Record<string, string>;
  gsc: Record<string, string>;
  local_falcon: Record<string, string>;
  google_ads_search: Record<string, string>;
};

type LocalConfigDraftResponse = {
  profile: string;
  path_label: string;
  exists: boolean;
  editable: boolean;
  draft: LocalConfigDraft;
  fields: LocalConfigField[];
  warnings: string[];
};

type LocalConfigChange = {
  provider: string;
  key: string;
  action: string;
  safe_value: string;
};

type LocalConfigPreview = {
  profile: string;
  path_label: string;
  would_create: boolean;
  would_update: boolean;
  normalized_config: LocalConfigDraft;
  changes: LocalConfigChange[];
  blocked: boolean;
  errors: string[];
  warnings: string[];
  saved?: boolean;
};

type ProfileRegistryOption = {
  key: string;
  label: string;
  status: string;
  kind: string;
  provider: string;
  expected_output_file: string;
};

type ProfileRegistryCapabilityDraft = {
  key: string;
  status: string;
};

type ProfileRegistryDraft = {
  slug: string;
  display_name: string;
  domain: string;
  vertical: string;
  service_model: string;
  data_sources: string[];
  capabilities: ProfileRegistryCapabilityDraft[];
};

type ProfileRegistryDraftResponse = {
  draft: ProfileRegistryDraft;
  provider_options: ProfileRegistryOption[];
  capability_options: ProfileRegistryOption[];
  warnings: string[];
};

type ProfileRegistryPreview = {
  registry_path_label: string;
  profile: Record<string, string | string[] | Array<Record<string, string>>>;
  expected_files: string[];
  changes: Array<Record<string, string>>;
  blocked: boolean;
  errors: string[];
  warnings: string[];
  saved?: boolean;
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
  credential_source?: string;
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

type OnboardingProviderStatus = {
  provider: string;
  label: string;
  enabled: boolean;
  expected_output_file: string;
  config_state: string;
  output_state: string;
  validation_state: string;
  copy_state: string;
  next_step: string;
};

type OnboardingStatus = {
  profile: {
    slug: string;
    display_name: string;
    route: string;
    shell_state: string;
    enabled_provider_count: number;
    configured_provider_count: number;
    output_ready_count: number;
    ready_for_copy_count: number;
  };
  local_config: {
    state: string;
    configured_provider_count: number;
    path_labels: string[];
  };
  vault: {
    state: string;
    local_falcon_api_key_metadata: string;
    locked: boolean;
  };
  validation: {
    state: string;
    folder_exists: boolean;
    overall_ok: boolean;
    last_validation: string;
    warning_count: number;
  };
  dashboard_copy: {
    state: string;
    ready_provider_count: number;
    last_copy: string;
  };
  providers: OnboardingProviderStatus[];
  safety: {
    read_only: boolean;
    no_provider_execution: boolean;
    no_fixture_copy: boolean;
    no_secret_values: boolean;
    no_file_contents: boolean;
  };
};

type OnboardingAction = {
  id: string;
  provider: string;
  provider_label: string;
  kind: string;
  label: string;
  description: string;
  status: string;
  available: boolean;
  unavailable_reason: string;
  requires_confirmation: boolean;
  read_only: boolean;
  local_only: boolean;
  writes_files: boolean;
  external_api: boolean;
  fixture_copy: boolean;
};

type OnboardingActionGroup = {
  provider: string;
  label: string;
  actions: OnboardingAction[];
};

type OnboardingActionsResponse = {
  profile: string;
  actions: OnboardingAction[];
  groups: OnboardingActionGroup[];
  safety: Record<string, boolean>;
};

type OnboardingActionRunResult = {
  profile: string;
  action: OnboardingAction;
  result: Record<string, boolean | number | string | null>;
  safety: Record<string, boolean>;
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
  onboarding_status: OnboardingStatus;
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
  const [localConfigDraft, setLocalConfigDraft] = useState<LocalConfigDraftResponse | null>(null);
  const [localConfigForm, setLocalConfigForm] = useState<LocalConfigDraft | null>(null);
  const [localConfigPreview, setLocalConfigPreview] = useState<LocalConfigPreview | null>(null);
  const [localConfigBusy, setLocalConfigBusy] = useState<boolean>(false);
  const [localConfigMessage, setLocalConfigMessage] = useState<string>('');
  const [localConfigConfirmed, setLocalConfigConfirmed] = useState<boolean>(false);
  const [profileRegistryDraft, setProfileRegistryDraft] = useState<ProfileRegistryDraftResponse | null>(null);
  const [profileRegistryForm, setProfileRegistryForm] = useState<ProfileRegistryDraft | null>(null);
  const [profileRegistryPreview, setProfileRegistryPreview] = useState<ProfileRegistryPreview | null>(null);
  const [profileRegistryBusy, setProfileRegistryBusy] = useState<boolean>(false);
  const [profileRegistryMessage, setProfileRegistryMessage] = useState<string>('');
  const [profileRegistryConfirmed, setProfileRegistryConfirmed] = useState<boolean>(false);
  const [onboardingActions, setOnboardingActions] = useState<OnboardingActionsResponse | null>(null);
  const [onboardingActionMessage, setOnboardingActionMessage] = useState<string>('');
  const [onboardingActionBusyId, setOnboardingActionBusyId] = useState<string>('');
  const [onboardingActionInputs, setOnboardingActionInputs] = useState<Record<string, string>>({});
  const [onboardingActionConfirmations, setOnboardingActionConfirmations] = useState<Record<string, boolean>>({});
  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.slug === selectedSlug),
    [profiles, selectedSlug],
  );

  useEffect(() => {
    refreshProfiles(setProfiles, setSelectedSlug, setError);
    refreshProfileRegistryDraft(
      setProfileRegistryDraft,
      setProfileRegistryForm,
      setProfileRegistryPreview,
      setProfileRegistryMessage,
      setProfileRegistryBusy,
      setProfileRegistryConfirmed,
    );
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
      setLocalConfigDraft(null);
      setLocalConfigForm(null);
      setLocalConfigPreview(null);
      setLocalConfigMessage('');
      setLocalConfigConfirmed(false);
      setOnboardingActions(null);
      setOnboardingActionMessage('');
      setOnboardingActionBusyId('');
      setOnboardingActionInputs({});
      setOnboardingActionConfirmations({});
      return;
    }
    setValidationConfirmed(false);
    setValidationResult(null);
    setCopyPreview(null);
    setCopyConfirmed(false);
    setCopyResult(null);
    setActionHistory(null);
    setLocalConfigDraft(null);
    setLocalConfigForm(null);
    setLocalConfigPreview(null);
    setLocalConfigMessage('');
    setLocalConfigConfirmed(false);
    setOnboardingActions(null);
    setOnboardingActionMessage('');
    setOnboardingActionBusyId('');
    setOnboardingActionInputs({});
    setOnboardingActionConfirmations({});
    refreshProfileStatus(
      selectedSlug,
      setDetail,
      setCopyPreview,
      setActionHistory,
      setError,
      setRefreshing,
      setStatusMessage,
    );
    refreshLocalConfigDraft(
      selectedSlug,
      setLocalConfigDraft,
      setLocalConfigForm,
      setLocalConfigPreview,
      setLocalConfigMessage,
      setLocalConfigBusy,
    );
    refreshOnboardingActions(selectedSlug, setOnboardingActions, setOnboardingActionMessage);
  }, [selectedSlug]);

  const refreshSelectedProfile = (message = 'Profile status refreshed', clearOnboardingMessage = true) => {
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
    refreshOnboardingActions(selectedSlug, setOnboardingActions, setOnboardingActionMessage, clearOnboardingMessage);
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

      <ProfileRegistryCreator
        busy={profileRegistryBusy}
        confirmed={profileRegistryConfirmed}
        draft={profileRegistryDraft}
        form={profileRegistryForm}
        message={profileRegistryMessage}
        preview={profileRegistryPreview}
        setConfirmed={setProfileRegistryConfirmed}
        setForm={setProfileRegistryForm}
        onPreview={() =>
          previewProfileRegistry(
            profileRegistryForm,
            setProfileRegistryPreview,
            setProfileRegistryMessage,
            setProfileRegistryBusy,
            setProfileRegistryConfirmed,
          )
        }
        onSave={() =>
          saveProfileRegistry(
            profileRegistryForm,
            profileRegistryConfirmed,
            setProfileRegistryPreview,
            setProfileRegistryMessage,
            setProfileRegistryBusy,
            setProfileRegistryConfirmed,
            () => {
              refreshProfiles(setProfiles, setSelectedSlug, setError);
              refreshProfileRegistryDraft(
                setProfileRegistryDraft,
                setProfileRegistryForm,
                setProfileRegistryPreview,
                setProfileRegistryMessage,
                setProfileRegistryBusy,
                setProfileRegistryConfirmed,
              );
            },
          )
        }
      />

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

              <OnboardingStatusDashboard status={detail.onboarding_status} />

              <OnboardingActionsPanel
                actions={onboardingActions}
                actionInputs={onboardingActionInputs}
                actionConfirmations={onboardingActionConfirmations}
                busyActionId={onboardingActionBusyId}
                message={onboardingActionMessage}
                onInputChange={(actionId, value) =>
                  setOnboardingActionInputs((current) => ({ ...current, [actionId]: value }))
                }
                onConfirmationChange={(actionId, confirmed) =>
                  setOnboardingActionConfirmations((current) => ({ ...current, [actionId]: confirmed }))
                }
                onRun={(actionId) =>
                  runOnboardingAction(
                    detail.slug,
                    actionId,
                    {
                      confirmed: Boolean(onboardingActionConfirmations[actionId]),
                      inputFile: onboardingActionInputs[actionId] ?? '',
                    },
                    setOnboardingActionBusyId,
                    setOnboardingActionMessage,
                    () => refreshSelectedProfile('Onboarding status refreshed after local action', false),
                  )
                }
              />

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

              <LocalConfigEditor
                busy={localConfigBusy}
                confirmed={localConfigConfirmed}
                draft={localConfigDraft}
                form={localConfigForm}
                message={localConfigMessage}
                preview={localConfigPreview}
                setConfirmed={setLocalConfigConfirmed}
                setForm={setLocalConfigForm}
                onPreview={() =>
                  previewLocalConfig(
                    detail.slug,
                    localConfigForm,
                    setLocalConfigPreview,
                    setLocalConfigMessage,
                    setLocalConfigBusy,
                    setLocalConfigConfirmed,
                  )
                }
                onSave={() =>
                  saveLocalConfig(
                    detail.slug,
                    localConfigForm,
                    localConfigConfirmed,
                    setLocalConfigPreview,
                    setLocalConfigMessage,
                    setLocalConfigBusy,
                    setLocalConfigConfirmed,
                    () => {
                      refreshLocalConfigDraft(
                        detail.slug,
                        setLocalConfigDraft,
                        setLocalConfigForm,
                        setLocalConfigPreview,
                        setLocalConfigMessage,
                        setLocalConfigBusy,
                      );
                      refreshSelectedProfile('Local profile config saved');
                    },
                  )
                }
              />

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

function OnboardingStatusDashboard({ status }: { status: OnboardingStatus }) {
  const enabledProviders = status.providers.filter((provider) => provider.enabled);
  const disabledProviders = status.providers.filter((provider) => !provider.enabled);

  return (
    <section className="onboarding-status-card" aria-label="Client Onboarding Status">
      <div className="onboarding-status-heading">
        <div>
          <span className="eyebrow">Read-only status</span>
          <h3>Client Onboarding Status</h3>
          <p>
            A compact view of profile setup, local readiness, safe output checks, and dashboard-lab copy readiness.
          </p>
        </div>
        <span className="badge neutral">{status.profile.route}</span>
      </div>

      <div className="onboarding-status-strip" aria-label="Profile onboarding summary">
        <StatusTile label="Profile shell" value={status.profile.shell_state} tone="ok" />
        <StatusTile label="Local config" value={status.local_config.state} tone={statusTone(status.local_config.state)} />
        <StatusTile label="Secret vault" value={status.vault.state} tone={statusTone(status.vault.state)} />
        <StatusTile label="Validation" value={status.validation.state} tone={statusTone(status.validation.state)} />
        <StatusTile label="Dashboard copy" value={status.dashboard_copy.state} tone={statusTone(status.dashboard_copy.state)} />
      </div>

      <div className="onboarding-provider-table" role="table" aria-label="Provider onboarding status">
        <div className="onboarding-provider-row header" role="row">
          <span role="columnheader">Provider</span>
          <span role="columnheader">Config</span>
          <span role="columnheader">Output</span>
          <span role="columnheader">Validation</span>
          <span role="columnheader">Copy</span>
          <span role="columnheader">Next</span>
        </div>
        {enabledProviders.map((provider) => (
          <ProviderStatusRow key={provider.provider} provider={provider} />
        ))}
      </div>

      {disabledProviders.length ? (
        <div className="disabled-provider-summary">
          <span>Not enabled</span>
          <div className="chip-row">
            {disabledProviders.map((provider) => (
              <span className="setup-chip" key={provider.provider}>{provider.label}</span>
            ))}
          </div>
        </div>
      ) : null}

      <p className="safe-copy-footnote">
        Read-only snapshot. No provider calls, fixture copy, local config write, registry write, vault unlock, or secret
        decryption is performed here.
      </p>
    </section>
  );
}

function StatusTile({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className={`status-tile ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProviderStatusRow({ provider }: { provider: OnboardingProviderStatus }) {
  return (
    <div className="onboarding-provider-row" role="row">
      <span role="cell">
        <strong>{provider.label}</strong>
        <small>{provider.expected_output_file || 'No summary file'}</small>
      </span>
      <span className={statusBadgeClass(provider.config_state)} role="cell">{provider.config_state}</span>
      <span className={statusBadgeClass(provider.output_state)} role="cell">{provider.output_state}</span>
      <span className={statusBadgeClass(provider.validation_state)} role="cell">{provider.validation_state}</span>
      <span className={statusBadgeClass(provider.copy_state)} role="cell">{provider.copy_state}</span>
      <span role="cell">{provider.next_step}</span>
    </div>
  );
}

function OnboardingActionsPanel({
  actions,
  actionInputs,
  actionConfirmations,
  busyActionId,
  message,
  onInputChange,
  onConfirmationChange,
  onRun,
}: {
  actions: OnboardingActionsResponse | null;
  actionInputs: Record<string, string>;
  actionConfirmations: Record<string, boolean>;
  busyActionId: string;
  message: string;
  onInputChange: (actionId: string, value: string) => void;
  onConfirmationChange: (actionId: string, confirmed: boolean) => void;
  onRun: (actionId: string) => void;
}) {
  return (
    <section className="onboarding-actions-card" aria-label="Onboarding Actions">
      <div className="onboarding-actions-heading">
        <div>
          <span className="eyebrow">Guarded local actions</span>
          <h3>Onboarding Actions</h3>
          <p>Safe checks and confirmed local aggregate imports are runnable here. Provider pulls, OAuth, and fixture copy remain disabled.</p>
        </div>
      </div>
      {message ? <p className="vault-message">{message}</p> : null}
      {actions ? (
        <div className="onboarding-action-groups">
          {actions.groups.map((group) => (
            <section className="onboarding-action-group" key={group.provider} aria-label={`${group.label} onboarding actions`}>
              <h4>{group.label}</h4>
              <div className="onboarding-action-list">
                {group.actions.map((action) => (
                  <OnboardingActionCard
                    action={action}
                    inputValue={actionInputs[action.id] ?? ''}
                    confirmed={Boolean(actionConfirmations[action.id])}
                    busy={busyActionId === action.id}
                    key={action.id}
                    onInputChange={(value) => onInputChange(action.id, value)}
                    onConfirmationChange={(confirmed) => onConfirmationChange(action.id, confirmed)}
                    onRun={() => onRun(action.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <p className="vault-message">Loading onboarding actions...</p>
      )}
    </section>
  );
}

function OnboardingActionCard({
  action,
  inputValue,
  confirmed,
  busy,
  onInputChange,
  onConfirmationChange,
  onRun,
}: {
  action: OnboardingAction;
  inputValue: string;
  confirmed: boolean;
  busy: boolean;
  onInputChange: (value: string) => void;
  onConfirmationChange: (confirmed: boolean) => void;
  onRun: () => void;
}) {
  const isFormFillsImport = action.id === 'form_fills.import-local';
  const isCallRailImport = action.id === 'callrail.import-local';
  const isLocalImport = isFormFillsImport || isCallRailImport;
  const runnable = action.available && !action.external_api && !action.fixture_copy && (
    (action.read_only && !action.writes_files) ||
    (isLocalImport && action.writes_files && confirmed && inputValue.trim().length > 0)
  );
  const stateLabel = action.available ? 'Available' : action.label.startsWith('Future:') ? 'Planned' : 'Unavailable';

  return (
    <article className="onboarding-action-card">
      <div className="card-heading">
        <div>
          <h5>{action.label}</h5>
          <p>{action.description}</p>
        </div>
        <span className={action.available ? 'badge ok' : 'badge neutral'}>{stateLabel}</span>
      </div>
      <div className="action-safety-row" aria-label={`${action.label} safety flags`}>
        <span>{action.read_only ? 'Read-only' : 'Writes possible'}</span>
        <span>{action.local_only ? 'Local-only' : 'External API'}</span>
        <span>{action.fixture_copy ? 'Fixture copy' : 'No fixture copy'}</span>
      </div>
      {!action.available && action.unavailable_reason ? (
        <p className="blocked-reason">{action.unavailable_reason}</p>
      ) : null}
      {isLocalImport ? (
        <div className="onboarding-import-controls">
          <label>
            <span>Local input file</span>
            <input
              type="text"
              value={inputValue}
              onChange={(event) => onInputChange(event.target.value)}
              placeholder={isCallRailImport ? 'qa-callrail.csv' : 'qa-form-fills.csv'}
              disabled={busy || !action.available}
            />
          </label>
          <label className="confirmation-row compact-confirmation">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => onConfirmationChange(event.target.checked)}
              disabled={busy || !action.available}
            />
            <span>{isCallRailImport ? 'I confirm this uses a local aggregate CallRail export and writes ignored local output only.' : 'I confirm this uses date-only local input and writes ignored local output only.'}</span>
          </label>
          <p className="safe-copy-footnote">
            {isCallRailImport
              ? 'No pasted call data, raw rows, caller names, phone numbers, recordings, transcripts, provider calls, OAuth, or fixture copy.'
              : 'No pasted form data, raw rows, PII, provider calls, OAuth, or fixture copy.'}
          </p>
        </div>
      ) : null}
      <button type="button" className="copy-button" disabled={!runnable || busy} onClick={onRun}>
        {busy ? 'Running...' : runnable ? (isCallRailImport ? 'Import aggregate export' : isFormFillsImport ? 'Import date-only file' : 'Run safe check') : 'Not runnable'}
      </button>
    </article>
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

function ProfileRegistryCreator({
  busy,
  confirmed,
  draft,
  form,
  message,
  preview,
  setConfirmed,
  setForm,
  onPreview,
  onSave,
}: {
  busy: boolean;
  confirmed: boolean;
  draft: ProfileRegistryDraftResponse | null;
  form: ProfileRegistryDraft | null;
  message: string;
  preview: ProfileRegistryPreview | null;
  setConfirmed: (confirmed: boolean) => void;
  setForm: (form: ProfileRegistryDraft) => void;
  onPreview: () => void;
  onSave: () => void;
}) {
  const providerOptions = draft?.provider_options ?? [];
  const capabilityOptions = draft?.capability_options ?? [];

  return (
    <section className="profile-registry-card" aria-label="Create new client profile">
      <div className="profile-registry-heading">
        <div>
          <span className="eyebrow">Tracked setup</span>
          <h3>Create new client profile</h3>
          <p>
            Drafts a tracked profile shell in <code>config/dashboard_lab_profiles.json</code>. This does not create
            dashboard-lab routes, local config, fixtures, providers, OAuth flows, or imports.
          </p>
        </div>
        <span className="badge neutral">Tracked config</span>
      </div>

      {draft?.warnings.length ? <p className="vault-message">{draft.warnings[0]}</p> : null}

      {form ? (
        <>
          <div className="profile-registry-fields">
            <label className="local-config-field">
              <span>Client display name</span>
              <input
                type="text"
                value={form.display_name}
                onChange={(event) => setForm({ ...form, display_name: event.target.value })}
              />
            </label>
            <label className="local-config-field">
              <span>Profile slug</span>
              <input
                type="text"
                value={form.slug}
                placeholder="new-client"
                onChange={(event) => setForm({ ...form, slug: event.target.value })}
              />
            </label>
            <label className="local-config-field">
              <span>Domain</span>
              <input
                type="text"
                value={form.domain}
                placeholder="example.com"
                onChange={(event) => setForm({ ...form, domain: event.target.value })}
              />
            </label>
            <label className="local-config-field">
              <span>Vertical</span>
              <input
                type="text"
                value={form.vertical}
                onChange={(event) => setForm({ ...form, vertical: event.target.value })}
              />
            </label>
            <label className="local-config-field wide-field">
              <span>Service model</span>
              <input
                type="text"
                value={form.service_model}
                onChange={(event) => setForm({ ...form, service_model: event.target.value })}
              />
            </label>
          </div>

          <div className="profile-registry-options">
            <div className="profile-registry-option-group">
              <h4>Provider outputs</h4>
              <p>Enabled providers determine profile data sources and tracked expected output readiness.</p>
              {providerOptions.map((option) => (
                <label className="confirmation-row compact-confirmation" key={option.key}>
                  <input
                    type="checkbox"
                    checked={form.data_sources.includes(option.key)}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        data_sources: toggleString(form.data_sources, option.key, event.target.checked),
                      })
                    }
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>

            <div className="profile-registry-option-group">
              <h4>Dashboard capabilities</h4>
              <p>These are profile rooms/capabilities only; they do not run providers or write fixtures.</p>
              {capabilityOptions.map((option) => {
                const existing = form.capabilities.find((item) => item.key === option.key);
                return (
                  <label className="confirmation-row compact-confirmation" key={option.key}>
                    <input
                      type="checkbox"
                      checked={Boolean(existing)}
                      onChange={(event) =>
                        setForm({
                          ...form,
                          capabilities: toggleCapability(form.capabilities, option, event.target.checked),
                        })
                      }
                    />
                    <span>{option.label} {existing?.status === 'planned' ? '(planned)' : ''}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="local-config-path">
            Generated labels:{' '}
            <code>{form.slug ? `/lab/${form.slug}` : '/lab/{slug}'}</code>{' '}
            <code>{form.slug ? `exports/local-real/dashboard-lab/${form.slug}` : 'exports/local-real/dashboard-lab/{slug}'}</code>
          </div>
        </>
      ) : (
        <p className="vault-message">Loading tracked profile draft...</p>
      )}

      {preview ? (
        <div className="local-config-preview" aria-label="Tracked profile preview">
          <h4>Preview</h4>
          {preview.errors.length ? (
            <ul className="error-list">
              {preview.errors.map((previewError) => (
                <li key={previewError}>{previewError}</li>
              ))}
            </ul>
          ) : (
            <>
              <p>
                Will append <strong>{String(preview.profile.display_name ?? '')}</strong> to{' '}
                <code>{preview.registry_path_label}</code>.
              </p>
              <div className="chip-row">
                {preview.expected_files.map((file) => (
                  <span className="file-chip" key={file}>{file}</span>
                ))}
              </div>
            </>
          )}
        </div>
      ) : null}

      {message ? <p className="vault-message">{message}</p> : null}

      <div className="local-config-actions">
        <button type="button" className="copy-button" disabled={busy || !form} onClick={onPreview}>
          {busy ? 'Working...' : 'Preview tracked profile'}
        </button>
        <label className="confirmation-row compact-confirmation">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={!preview || preview.blocked}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>I confirm this writes tracked safe profile metadata only.</span>
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={busy || !preview || preview.blocked || !confirmed}
          onClick={onSave}
        >
          Save tracked profile shell
        </button>
      </div>
    </section>
  );
}

function LocalConfigEditor({
  busy,
  confirmed,
  draft,
  form,
  message,
  preview,
  setConfirmed,
  setForm,
  onPreview,
  onSave,
}: {
  busy: boolean;
  confirmed: boolean;
  draft: LocalConfigDraftResponse | null;
  form: LocalConfigDraft | null;
  message: string;
  preview: LocalConfigPreview | null;
  setConfirmed: (confirmed: boolean) => void;
  setForm: (form: LocalConfigDraft) => void;
  onPreview: () => void;
  onSave: () => void;
}) {
  const fields = draft?.fields ?? [];

  return (
    <section className="local-config-card" aria-label="Local profile config setup">
      <div className="local-config-heading">
        <div>
          <span className="eyebrow">Local setup</span>
          <h3>Set up local config</h3>
          <p>
            Create or update the ignored per-profile config file. Do not paste secret values, OAuth JSON, API keys, raw
            CSV rows, or customer data.
          </p>
        </div>
        <span className={draft?.exists ? 'badge ok' : 'badge warn'}>{draft?.exists ? 'Exists' : 'Missing'}</span>
      </div>

      {draft ? (
        <div className="local-config-path">
          Target: <code>{draft.path_label}</code>
        </div>
      ) : (
        <p className="vault-message">Loading local config draft...</p>
      )}

      {form ? (
        <div className="local-config-sections">
          <LocalConfigProviderSection
            description="Use env var names only; real GA4 IDs and OAuth paths stay in the local shell or env file."
            fields={fields.filter((field) => field.provider === 'ga4')}
            form={form}
            provider="ga4"
            title="GA4"
            setForm={setForm}
          />
          <LocalConfigProviderSection
            description="Site URL is safe operational metadata; OAuth file locations remain env var references."
            fields={fields.filter((field) => field.provider === 'gsc')}
            form={form}
            provider="gsc"
            title="GSC"
            setForm={setForm}
          />
          <LocalConfigProviderSection
            description="Manifest path is an ignored local reference. API key value belongs in env or the encrypted vault."
            fields={fields.filter((field) => field.provider === 'local_falcon')}
            form={form}
            provider="local_falcon"
            title="Local Falcon"
            setForm={setForm}
          />
          <LocalConfigProviderSection
            description="Google Ads remains read-only reporting and planned-only in this local config editor."
            fields={fields.filter((field) => field.provider === 'google_ads_search')}
            form={form}
            provider="google_ads_search"
            title="Google Ads Search"
            setForm={setForm}
          />
          <div className="local-config-disabled">
            <strong>Not editable in v1:</strong> CallRail and Form Fills path references stay manual until their
            per-profile schema is added.
          </div>
        </div>
      ) : null}

      {preview ? (
        <div className="local-config-preview" aria-label="Local config preview">
          <h4>Preview</h4>
          <p>
            {preview.would_create ? 'Will create' : 'Will update'} <code>{preview.path_label}</code>
          </p>
          {preview.errors.length ? (
            <ul className="error-list">
              {preview.errors.map((previewError) => (
                <li key={previewError}>{previewError}</li>
              ))}
            </ul>
          ) : preview.changes.length ? (
            <ul className="status-list">
              {preview.changes.map((change) => (
                <li key={`${change.provider}-${change.key}`}>
                  <span className="tiny-dot ok" />
                  <span>
                    {providerLabel(change.provider)} {humanizeKey(change.key)}: {change.safe_value || 'Cleared'}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p>No field changes detected.</p>
          )}
        </div>
      ) : null}

      {message ? <p className="vault-message">{message}</p> : null}

      <div className="local-config-actions">
        <button type="button" className="copy-button" disabled={busy || !form} onClick={onPreview}>
          {busy ? 'Working...' : 'Preview local config changes'}
        </button>
        <label className="confirmation-row compact-confirmation">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={!preview || preview.blocked}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>I confirm this writes only ignored local config and contains no secrets or raw data.</span>
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={busy || !preview || preview.blocked || !confirmed}
          onClick={onSave}
        >
          Save ignored local config
        </button>
      </div>
    </section>
  );
}

function LocalConfigProviderSection({
  description,
  fields,
  form,
  provider,
  title,
  setForm,
}: {
  description: string;
  fields: LocalConfigField[];
  form: LocalConfigDraft;
  provider: keyof LocalConfigDraft;
  title: string;
  setForm: (form: LocalConfigDraft) => void;
}) {
  const providerForm = form[provider] as Record<string, string>;

  return (
    <section className="local-config-provider" aria-label={`${title} local config`}>
      <div>
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      <div className="local-config-fields">
        {fields.map((field) => (
          <label className="local-config-field" key={`${field.provider}-${field.key}`}>
            <span>{field.label}</span>
            <input
              type="text"
              value={providerForm[field.key] ?? ''}
              disabled={field.kind === 'planned_status'}
              placeholder={fieldPlaceholder(field)}
              onChange={(event) =>
                setForm({
                  ...form,
                  [provider]: {
                    ...providerForm,
                    [field.key]: event.target.value,
                  },
                })
              }
            />
          </label>
        ))}
      </div>
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
        {item.credential_source ? (
          <div>
            <dt>Credentials</dt>
            <dd>{item.credential_source}</dd>
          </div>
        ) : null}
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

function statusTone(value: string) {
  if (value.includes('Configured') || value.includes('created') || value.includes('exists') || value.includes('Ready')) {
    return 'ok';
  }
  if (value.includes('Not enabled') || value.includes('Not applicable') || value.includes('unknown') || value.includes('Not configured')) {
    return 'neutral';
  }
  return 'warn';
}

function statusBadgeClass(value: string) {
  const tone = statusTone(value);
  if (tone === 'ok') {
    return 'badge ok';
  }
  if (tone === 'neutral') {
    return 'badge neutral';
  }
  return 'badge warn';
}

function humanizeKey(value: string) {
  const labels: Record<string, string> = {
    api_key_env_present: 'Configured via env var',
    api_key_vault_configured: 'Configured via vault',
    api_key_vault_locked: 'Vault locked',
    api_key_visible: 'API key configured',
  };
  if (labels[value]) {
    return labels[value];
  }
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function yesNo(value: boolean) {
  return value ? 'Yes' : 'No';
}

function cloneProfileRegistryDraft(draft: ProfileRegistryDraft): ProfileRegistryDraft {
  return {
    slug: draft.slug,
    display_name: draft.display_name,
    domain: draft.domain,
    vertical: draft.vertical,
    service_model: draft.service_model,
    data_sources: [...draft.data_sources],
    capabilities: draft.capabilities.map((item) => ({ ...item })),
  };
}

function toggleString(values: string[], key: string, checked: boolean) {
  if (checked) {
    return values.includes(key) ? values : [...values, key];
  }
  return values.filter((value) => value !== key);
}

function toggleCapability(
  values: ProfileRegistryCapabilityDraft[],
  option: ProfileRegistryOption,
  checked: boolean,
) {
  if (checked) {
    return values.some((item) => item.key === option.key)
      ? values
      : [...values, { key: option.key, status: option.status || 'enabled' }];
  }
  return values.filter((value) => value.key !== option.key);
}

function refreshProfiles(
  setProfiles: (profiles: ProfileSummary[]) => void,
  setSelectedSlug: (slug: string) => void,
  setError: (error: string) => void,
) {
  fetchJson<{ profiles: ProfileSummary[] }>(`${API_BASE}/api/profiles`)
    .then((payload) => {
      setProfiles(payload.profiles);
      setSelectedSlug(payload.profiles[0]?.slug ?? '');
    })
    .catch((fetchError: Error) => setError(fetchError.message));
}

function refreshProfileRegistryDraft(
  setDraft: (draft: ProfileRegistryDraftResponse | null) => void,
  setForm: (form: ProfileRegistryDraft | null) => void,
  setPreview: (preview: ProfileRegistryPreview | null) => void,
  setMessage: (message: string) => void,
  setBusy: (busy: boolean) => void,
  setConfirmed: (confirmed: boolean) => void,
) {
  setBusy(true);
  fetchJson<ProfileRegistryDraftResponse>(`${API_BASE}/api/profile-registry/new-draft`)
    .then((payload) => {
      setDraft(payload);
      setForm(cloneProfileRegistryDraft(payload.draft));
      setPreview(null);
      setMessage('');
      setConfirmed(false);
    })
    .catch((fetchError: Error) => setMessage(safeProfileRegistryErrorMessage(fetchError)))
    .finally(() => setBusy(false));
}

function previewProfileRegistry(
  form: ProfileRegistryDraft | null,
  setPreview: (preview: ProfileRegistryPreview | null) => void,
  setMessage: (message: string) => void,
  setBusy: (busy: boolean) => void,
  setConfirmed: (confirmed: boolean) => void,
) {
  if (!form) {
    setMessage('Tracked profile draft is still loading.');
    return;
  }
  setBusy(true);
  setConfirmed(false);
  fetch(`${API_BASE}/api/profile-registry/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft: form }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<ProfileRegistryPreview>;
    })
    .then((payload) => {
      setPreview(payload);
      setMessage(payload.blocked ? 'Preview found tracked profile validation issues.' : 'Preview ready. Review tracked config changes before saving.');
    })
    .catch((fetchError: Error) => setMessage(safeProfileRegistryErrorMessage(fetchError)))
    .finally(() => setBusy(false));
}

function saveProfileRegistry(
  form: ProfileRegistryDraft | null,
  confirmed: boolean,
  setPreview: (preview: ProfileRegistryPreview | null) => void,
  setMessage: (message: string) => void,
  setBusy: (busy: boolean) => void,
  setConfirmed: (confirmed: boolean) => void,
  onComplete: () => void,
) {
  if (!form) {
    setMessage('Tracked profile draft is still loading.');
    return;
  }
  setBusy(true);
  fetch(`${API_BASE}/api/profile-registry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft: form, confirmed }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<ProfileRegistryPreview>;
    })
    .then((payload) => {
      setPreview(payload);
      setConfirmed(false);
      setMessage('Tracked profile shell saved.');
      onComplete();
    })
    .catch((fetchError: Error) => setMessage(safeProfileRegistryErrorMessage(fetchError)))
    .finally(() => setBusy(false));
}

function fieldPlaceholder(field: LocalConfigField) {
  if (field.kind === 'env_var_name') {
    return 'PROFILE_PROVIDER_SETTING';
  }
  if (field.kind === 'site_url') {
    return 'sc-domain:example.com';
  }
  if (field.kind === 'path_reference') {
    return 'local-falcon-manifests/profile.local.json';
  }
  return 'planned';
}

function cloneLocalConfigDraft(draft: LocalConfigDraft): LocalConfigDraft {
  return {
    profile: draft.profile,
    ga4: { ...draft.ga4 },
    gsc: { ...draft.gsc },
    local_falcon: { ...draft.local_falcon },
    google_ads_search: { ...draft.google_ads_search },
  };
}

function refreshLocalConfigDraft(
  profileSlug: string,
  setDraft: (draft: LocalConfigDraftResponse | null) => void,
  setForm: (form: LocalConfigDraft | null) => void,
  setPreview: (preview: LocalConfigPreview | null) => void,
  setMessage: (message: string) => void,
  setBusy: (busy: boolean) => void,
) {
  setBusy(true);
  fetchJson<LocalConfigDraftResponse>(`${API_BASE}/api/profiles/${profileSlug}/local-config/draft`)
    .then((payload) => {
      setDraft(payload);
      setForm(cloneLocalConfigDraft(payload.draft));
      setPreview(null);
      setMessage('');
    })
    .catch((fetchError: Error) => setMessage(safeLocalConfigErrorMessage(fetchError)))
    .finally(() => setBusy(false));
}

function previewLocalConfig(
  profileSlug: string,
  form: LocalConfigDraft | null,
  setPreview: (preview: LocalConfigPreview | null) => void,
  setMessage: (message: string) => void,
  setBusy: (busy: boolean) => void,
  setConfirmed: (confirmed: boolean) => void,
) {
  if (!form) {
    setMessage('Local config draft is still loading.');
    return;
  }
  setBusy(true);
  setConfirmed(false);
  fetch(`${API_BASE}/api/profiles/${profileSlug}/local-config/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft: form }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<LocalConfigPreview>;
    })
    .then((payload) => {
      setPreview(payload);
      setMessage(payload.blocked ? 'Preview found local config validation issues.' : 'Preview ready. Review changes before saving.');
    })
    .catch((fetchError: Error) => setMessage(safeLocalConfigErrorMessage(fetchError)))
    .finally(() => setBusy(false));
}

function saveLocalConfig(
  profileSlug: string,
  form: LocalConfigDraft | null,
  confirmed: boolean,
  setPreview: (preview: LocalConfigPreview | null) => void,
  setMessage: (message: string) => void,
  setBusy: (busy: boolean) => void,
  setConfirmed: (confirmed: boolean) => void,
  onComplete: () => void,
) {
  if (!form) {
    setMessage('Local config draft is still loading.');
    return;
  }
  setBusy(true);
  fetch(`${API_BASE}/api/profiles/${profileSlug}/local-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft: form, confirmed }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<LocalConfigPreview>;
    })
    .then((payload) => {
      setPreview(payload);
      setConfirmed(false);
      setMessage('Ignored local profile config saved.');
      onComplete();
    })
    .catch((fetchError: Error) => setMessage(safeLocalConfigErrorMessage(fetchError)))
    .finally(() => setBusy(false));
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

function refreshOnboardingActions(
  profileSlug: string,
  setActions: (actions: OnboardingActionsResponse | null) => void,
  setMessage: (message: string) => void,
  clearMessage = true,
) {
  fetchJson<OnboardingActionsResponse>(`${API_BASE}/api/profiles/${profileSlug}/onboarding-actions`)
    .then((payload) => {
      setActions(payload);
      if (clearMessage) {
        setMessage('');
      }
    })
    .catch((fetchError: Error) => setMessage(safeOnboardingActionErrorMessage(fetchError)));
}

function runOnboardingAction(
  profileSlug: string,
  actionId: string,
  options: { confirmed: boolean; inputFile: string },
  setBusyActionId: (actionId: string) => void,
  setMessage: (message: string) => void,
  onComplete?: () => void,
) {
  setBusyActionId(actionId);
  fetch(`${API_BASE}/api/profiles/${profileSlug}/onboarding-actions/${actionId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      confirmed: options.confirmed,
      input_file: options.inputFile.trim() || undefined,
    }),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      return response.json() as Promise<OnboardingActionRunResult>;
    })
    .then((payload) => {
      const status = String(payload.result.status ?? 'ok');
      const message = String(payload.result.message ?? 'Action completed.');
      setMessage(`${payload.action.provider_label}: ${safeOnboardingActionResultMessage(status, message)}`);
      if ((payload.action.id === 'form_fills.import-local' || payload.action.id === 'callrail.import-local') && status === 'ok') {
        onComplete?.();
      }
    })
    .catch((fetchError: Error) => setMessage(safeOnboardingActionErrorMessage(fetchError)))
    .finally(() => setBusyActionId(''));
}

function safeOnboardingActionResultMessage(status: string, message: string) {
  if (status === 'input_missing') {
    return 'Input missing.';
  }
  if (status === 'rejected') {
    return 'Unsafe input rejected.';
  }
  if (status === 'failed') {
    return message.includes('Validation failed') ? 'Validation failed.' : 'Import failed.';
  }
  if (status === 'passed') {
    return 'Validation passed.';
  }
  return message;
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

function safeLocalConfigErrorMessage(error: Error) {
  const status = error.message.match(/\d{3}/)?.[0] ?? '';
  if (status === '400') {
    return 'Local config request was rejected by safety validation.';
  }
  if (status === '404') {
    return 'Profile was not found.';
  }
  return status ? `Local config request failed with status ${status}.` : 'Local config request failed.';
}

function safeProfileRegistryErrorMessage(error: Error) {
  const status = error.message.match(/\d{3}/)?.[0] ?? '';
  if (status === '400') {
    return 'Tracked profile request was rejected by safety validation.';
  }
  return status ? `Tracked profile request failed with status ${status}.` : 'Tracked profile request failed.';
}

function safeOnboardingActionErrorMessage(error: Error) {
  const status = error.message.match(/\d{3}/)?.[0] ?? '';
  if (status === '400') {
    return 'Onboarding action was blocked by guardrails.';
  }
  if (status === '404') {
    return 'Onboarding action or profile was not found.';
  }
  return status ? `Onboarding action failed with status ${status}.` : 'Onboarding action failed.';
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
