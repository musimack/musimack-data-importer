# Credential and Secret Manager architecture

## Production model

Use a hybrid identity model:

- Cloud Run uses a dedicated Google Cloud service account through workload identity; no service-account key file is created.
- GA4 and Search Console initially use one or more Musimack-controlled OAuth authorizations stored as refresh grants in Secret Manager, because existing validated logic and likely property access are user-grant based.
- BigQuery uses the Cloud Run service account directly with dataset-level IAM.
- Google Ads later uses a Secret Manager OAuth refresh grant plus OAuth client secret and developer token; customer IDs remain non-secret mappings.
- A client may require a separate OAuth authorization when it cannot grant access to the shared Musimack principal, has distinct revocation/contract requirements, or needs a separate consent/audit boundary.

The default is **one Musimack authorization per provider and environment where least privilege remains understandable**, not one token per project and not one universal token for every Google API. The configuration model permits per-client grants without changing code.

## Credential option comparison

| Option                         | Production use                                            | Finding                                                                                                                                                                  |
| ------------------------------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Local token files              | Local development/bootstrap only                          | Validated today but tied to workstation, writable disk, and browser flow                                                                                                 |
| Secret Manager                 | **Recommended provider-secret store**                     | IAM, versioning, audit logs, rotation workflows, Cloud Run integration                                                                                                   |
| Portal encrypted credential DB | Do not use for provider retrieval                         | Expands public Portal blast radius and contradicts final retrieval ownership; retain existing boundary only for legacy/disabled portal features until separately retired |
| Service accounts               | BigQuery and GA4 where the client grants access           | Preferred keyless workload identity; GSC/Ads applicability depends on provider permissions                                                                               |
| Workload identity              | **Required for Cloud Run**                                | Eliminates downloadable runtime keys                                                                                                                                     |
| One shared OAuth grant         | Default where Musimack account has all approved resources | Low operational count, wider revocation/blast radius                                                                                                                     |
| Per-client OAuth grant         | Exception or client requirement                           | Strong isolation, high onboarding/rotation burden                                                                                                                        |

## Secret inventory and naming

Illustrative names, subject to `PO-006`:

```text
prod-google-oauth-client
prod-ga4-oauth-grant-musimack-reporting-01
prod-gsc-oauth-grant-musimack-reporting-01
prod-google-ads-oauth-grant-musimack-reporting-01
prod-google-ads-developer-token
```

Use labels for environment, provider, owner, authorization principal, rotation class, and data classification. Do not put client names, property IDs, site URLs, tokens, or account IDs in secret payload logs. The Portal's `credential_binding_key` is stable even when the backing secret version changes.

## Secret contents

- OAuth client registration: minimum fields required for token refresh.
- OAuth grant: refresh token, token endpoint, scopes, authorization principal, and a safe grant schema version. Do not persist transient access tokens unless a provider library absolutely requires it; prefer in-memory access tokens.
- Google Ads developer token: separate secret from OAuth grant.
- No GA4 property, GSC site, customer ID, BigQuery dataset, Portal project UUID, or output path is secret payload material.

## Runtime resolution

1. Job retrieves sanitized configuration and validates the credential binding before secret access.
2. Credential provider requests the exact bound secret version through the Cloud API or a read-only mounted file.
3. Adapter parses in memory, exchanges refresh grant for an access token, and constructs the provider client.
4. Access token stays in memory and is never returned, logged, or written to the job filesystem.
5. Job discards credential objects at process exit.

Do not let current GA4/GSC library fallback invoke `InstalledAppFlow` in cloud mode. Do not call current `save_oauth_credentials` from cloud mode. Refactor those behaviors behind `CredentialProvider` and `CredentialRefreshPolicy` interfaces while retaining the local adapter.

## Rotation and revocation

- Rotate OAuth client secrets only through a dual-version rehearsal; existing refresh grants may be tied to the prior client.
- Add a new Secret Manager version, run metadata-only readiness, run a one-call permission probe, complete a bounded manual import, then disable the prior version after rollback time expires.
- Revocation immediately disables affected Portal provider configurations and blocks new runs before secret access.
- A runtime-detected `invalid_grant` becomes `credential_revoked_or_invalid`, never a raw provider message.
- Secret deletion is delayed and separately approved. Version disablement is the normal rollback.
- Secret Manager audit logs and Portal configuration audit events are both retained; neither contains payload values.
- Backups restore secret metadata/IAM/IaC, but OAuth grants may require reauthorization. Recovery plans must not assume a deleted/revoked refresh token can be reconstructed.

## Least privilege

Runtime service account needs only:

- execute as the Cloud Run Job service identity;
- access listed secret versions;
- write its own Cloud Logging/Monitoring telemetry;
- invoke/read the exact Portal ingestion/configuration audience as authorized by the Portal;
- later, create BigQuery jobs in the billing project and read only mapped datasets.

It does not need Portal database access, Secret Manager administration, project Owner/Editor, IAM mutation, Scheduler administration, Artifact Registry write, or access to unrelated secrets.

Human deployer, OAuth authorizer, runtime job, Portal workload verifier, and scheduler identities are distinct roles.

## Local development

Local mode may continue using external token files and `.local.json`/environment references. It must:

- reject credential paths inside the repository;
- use separate GA4 and GSC token caches;
- label evidence `local_live` or `fixture`, never `cloud_production`;
- prevent production Portal ingestion by default;
- bootstrap OAuth interactively only through a dedicated command;
- support a fixture credential provider that never opens real secret files;
- optionally allow developer Secret Manager access through personal Application Default Credentials only after explicit environment selection and IAM grant; no Secret Manager emulator is required.

Production profile JSON contains no credential path. The same application service accepts a local `FileCredentialProvider` or cloud `SecretManagerCredentialProvider`, selected by an explicit environment adapter.

## Safe logging rules

Never log secret resource payloads, token fingerprints derived from secret values, authorization headers, OAuth codes, client IDs/secrets, access/refresh tokens, service-account JSON, local credential paths, raw provider errors, or full configuration objects. Safe fields are provider, project UUID, binding key, secret version label, ready/missing/disabled classification, and closed error code.
