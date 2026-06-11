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

type ProfileSummary = {
  slug: string;
  display_name: string;
  domain: string;
  vertical: string;
  service_model: string;
  dashboard_lab_route: string;
  enabled_providers: string[];
  provider_readiness: ProviderReadiness[];
};

type ProfileDetail = ProfileSummary & {
  paths: {
    local_real_output_folder: string;
    dashboard_lab_local_fixture_folder: string;
  };
  output_status: OutputStatus;
  action_plan: ActionPlan;
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

              <dl className="profile-grid">
                <div>
                  <dt>Vertical</dt>
                  <dd>{detail.vertical}</dd>
                </div>
                <div>
                  <dt>Service model</dt>
                  <dd>{detail.service_model}</dd>
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

              <LastActionSummary lastActions={detail.last_actions} />

              <h3>Data Source Readiness</h3>
              <div className="readiness-grid">
                {detail.provider_readiness.map((provider) => (
                  <article className="readiness-card" key={provider.provider}>
                    <div className="card-heading">
                      <h4>{provider.label}</h4>
                      <span className={provider.config_ready ? 'badge ok' : 'badge warn'}>
                        {provider.config_ready ? 'Ready' : 'Needs config'}
                      </span>
                    </div>
                    <dl>
                      <div>
                        <dt>Enabled</dt>
                        <dd>{yesNo(provider.enabled)}</dd>
                      </div>
                      <div>
                        <dt>Credentials</dt>
                        <dd>{yesNo(provider.credentials_ready)}</dd>
                      </div>
                      <div>
                        <dt>Expected file</dt>
                        <dd>{provider.expected_output_file}</dd>
                      </div>
                      <div>
                        <dt>Output exists</dt>
                        <dd>{yesNo(provider.output_file_exists)}</dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>

              <h3>Output Folder Status</h3>
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
                    No provider calls, no portal action, and never committed <code>public/fixtures</code>.
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

              <h3>Action Plan</h3>
              <div className="action-grid">
                {detail.action_plan.actions.map((action) => (
                  <article className="action-card" key={action.id}>
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
                          <span>Preview command</span>
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
                ))}
              </div>
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
    profile: 'Profile Output',
    dashboard_lab: 'Dashboard Lab',
  };
  return labels[provider] ?? provider;
}

function actionLabel(actionId: string) {
  const labels: Record<string, string> = {
    'validate-output': 'Validate output',
    'copy-to-dashboard-lab': 'Copy to dashboard-lab',
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
