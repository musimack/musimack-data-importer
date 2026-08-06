# Ownership, configuration, and canonical identity

## Final ownership matrix

`A` means authoritative owner. `E` means execution/consumer responsibility under an explicit contract. A row has only one authoritative owner.

| Concern                        | Data Importer                                              | Client Portal                                   | Google Cloud platform                                   |
| ------------------------------ | ---------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------- |
| Provider calls                 | **A**                                                      | Prohibited                                      | Network/runtime support                                 |
| OAuth application registration | Operator/client of configuration                           | None                                            | **A** for registered Google OAuth resource              |
| OAuth refresh credentials      | Resolve/use in memory                                      | Opaque binding only                             | **A** for encrypted secret value in Secret Manager      |
| Secret references              | **E** resolve and validate                                 | **A** bind project/provider to opaque reference | Enforce referenced secret/IAM                           |
| GA4 property mapping           | Consume                                                    | **A**                                           | None                                                    |
| GSC site mapping               | Consume                                                    | **A**                                           | None                                                    |
| Google Ads account mapping     | Consume                                                    | **A**                                           | None                                                    |
| BigQuery dataset mapping       | Consume                                                    | **A**                                           | Dataset exists and IAM enforced                         |
| Canonical client identity      | Consume UUID                                               | **A**                                           | None                                                    |
| Canonical project identity     | Consume UUID                                               | **A**                                           | None                                                    |
| Provider normalization         | **A**                                                      | Contract validation only                        | None                                                    |
| Weekly revision validation     | Prevalidate/conformance                                    | **A**                                           | None                                                    |
| Weekly revision persistence    | Deliver only                                               | **A**                                           | Database availability                                   |
| Current revision pointers      | None                                                       | **A**                                           | None                                                    |
| Dashboard presentation         | None                                                       | **A**                                           | Hosting support                                         |
| Immutable publications         | None                                                       | **A**                                           | Backup/storage support                                  |
| Scheduling                     | Job supports invocation                                    | Policy/readiness signal                         | **A** execution only after approval                     |
| Logging and alerting           | Emit domain-safe structured events                         | Emit ingestion/persistence events               | **A** collection, routing, retention                    |
| Cost ceilings                  | **A** enforce per provider/query                           | Store approved policy/version                   | **A** budgets/alerts are backstop                       |
| Backup and recovery            | Back up code/config metadata; secrets reauthorization plan | **A** database recovery                         | **A** managed backup copies, secret metadata, IaC state |

## Canonical production source of truth

The Portal database is the canonical configuration source because it already owns durable client/project UUIDs, project-to-client relationships, domains, access scoping, and provider mapping foundations. A new governed configuration aggregate should extend, not duplicate, those identities.

Minimum logical record:

```text
project_ingestion_configuration.v1
  client_id (Portal UUID, immutable reference)
  project_id (Portal UUID, immutable reference)
  client_name (display only)
  project_name (display only)
  project_slug (unique durable operator label; new governed field)
  reporting_timezone (IANA name)
  root_domain / allowed_hosts
  provider
  external_resource_type
  external_resource_id
  optional isolation_filter (versioned; absent by default)
  credential_binding_key (opaque, non-secret)
  enabled
  request_ceiling_policy_id + version
  freshness_policy_id + version
  pilot_state
  scheduling_state
  configuration_version
  updated_at / updated_by / audit event
```

The importer fetches this record through a read-only service endpoint, caches it only for the execution, and stamps `configuration_identity` and `configuration_version` into run evidence. It refuses disabled, ambiguous, unsupported, stale, or cross-project mappings.

## Synchronization contract

- Portal writes configuration through an admin-only, audited workflow.
- Importer never writes canonical mappings.
- Every job requests an exact configuration version or receives the latest enabled version and records it.
- Provider calls do not begin if the returned version differs from an operator-pinned version.
- The Portal ingestion endpoint checks that the submitted configuration identity/version still belongs to the project/provider.
- Resource identity changes create a new configuration version; historical runs retain the prior identity.
- Deleting a project/provider mapping is prohibited when referenced by run evidence. Disable and supersede it instead.

## Secret references without a second registry

`credential_binding_key` is a stable non-secret identity such as `google-oauth-grant/musimack-reporting-01`. The production adapter derives or resolves the environment-specific Secret Manager resource through a controlled naming rule. The mapping record does not carry a token or client secret. Secret version selection is deployment/config policy and is logged only as a safe version label, never a value.

## Local profile mapping

Existing `.local.json` profiles remain a development adapter, not a production database.

| Local field                | Production mapping                                               |
| -------------------------- | ---------------------------------------------------------------- |
| `profile` / alias          | `project_slug`; resolved to Portal `project_id` before execution |
| `ga4.property_id`          | provider resource mapping with `resource_type=ga4_property`      |
| `gsc.site_url`             | provider resource mapping with `resource_type=gsc_site`          |
| credential file/env fields | `credential_binding_key`; local adapter may still resolve files  |
| Google Ads customer ID     | `resource_type=google_ads_customer`                              |
| domain                     | Portal project `root_domain` and allowed hosts                   |
| output path                | local-only adapter; absent from cloud contract                   |

Configuration precedence:

1. explicit safe CLI override for local/dev only;
2. selected environment adapter;
3. local profile file for local development or Portal configuration API for cloud;
4. defaults limited to non-security behavior.

Production refuses local file paths, inline service-account JSON, browser OAuth, unversioned mappings, and a `local` evidence label. Local mode refuses production Portal writes unless a separate explicit environment and write gate are present.

## Identity design consequences

- Names and domains are not ingestion authorization. UUID relationships are authoritative.
- A profile slug is operator convenience, not a cross-repository primary key.
- Provider resource IDs are non-secret but sensitive configuration and are omitted from client-facing APIs/logs.
- One provider resource may map to multiple projects only through an approved, versioned isolation filter that proves rows cannot cross project boundaries.
- One credential grant may serve several provider mappings; revocation impact must be visible before a change.

## Coin Meter recommendation

Represent **Coin Meter as one client with two projects** (`Coin Meter` and `Coin Meter Support Portal`) if the same customer organization, contracting/access boundary, and Portal viewers apply. The current Portal model naturally supports one client with multiple projects, and live-weekly storage scopes every cycle/revision to a project/client pair.

Do not model both sites as one project merely because they share credentials. If they have separate GA4 properties, map one property to each project. If they share a property, onboarding is blocked until either:

- separate properties are created; or
- an explicit `ga4_property_filter.v1` hostname/stream isolation contract is implemented, validated, and accepted.

The existing mapping model does not hold an accepted hostname/stream filter, so the architecture does not silently decide that shared-property data can be separated safely. Use two clients only if legal ownership, access audience, retention, or reporting governance differs; David decides this in `PO-014`.
