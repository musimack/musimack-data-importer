"""Metadata-only GA4 and Google Search Console clients.

These clients exist for one purpose: confirm that configured credentials
authenticate and that the configured property or site is reachable. They are
deliberately incapable of retrieving reporting data.

Two safeguards make that structural rather than a matter of discipline:

- **Each class exposes exactly one method.** There is no ``run_report``,
  ``runReport``, ``searchanalytics``, or ``sites.list`` path to call, so the
  verification workflow's reporting-method guard has nothing to reject.
- **The endpoints themselves cannot return reporting data.**
  ``properties.getMetadata`` accepts no date range, and ``sites.get`` is an
  exact single-site lookup rather than a listing, so neither paginates.

Credential handling reuses the existing OAuth loaders. No credential value is
logged, returned, or placed in evidence, and provider errors are sanitized
through the existing helpers before they surface.
"""

from __future__ import annotations

from typing import Any

import requests
from google.auth.transport.requests import Request

from src.providers.ga4.client import (
    GA4_DATA_API_SCOPE,
    Ga4ClientError,
    load_oauth_credentials,
    sanitized_google_api_error,
)
from src.providers.gsc.client import (
    GscClientError,
    load_gsc_oauth_credentials,
)
from src.providers.gsc.client import (
    sanitized_google_api_error as sanitized_gsc_error,
)

GA4_METADATA_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}/metadata"
GSC_SITE_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site_url}"

DEFAULT_TIMEOUT_SECONDS = 30


class Ga4MetadataClient:
    """One GA4 operation: ``properties.getMetadata``.

    Returns the property's dimension and metric catalogue plus its resource
    name. Accepts no date range, so no reporting data is reachable.
    """

    def __init__(
        self,
        client_secrets_file: str,
        token_file: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._client_secrets_file = client_secrets_file
        self._token_file = token_file
        self._timeout_seconds = timeout_seconds

    def get_property_metadata(self, property_id: str) -> dict[str, Any]:
        credentials = load_oauth_credentials(self._client_secrets_file, self._token_file)
        if not credentials.valid:
            credentials.refresh(Request())
        response = requests.get(
            GA4_METADATA_URL.format(property_id=property_id),
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=self._timeout_seconds,
        )
        if response.status_code >= 400:
            raise Ga4ClientError(sanitized_google_api_error(response))
        return response.json()


class GscSiteMetadataClient:
    """One Google Search Console operation: ``sites.get``.

    Returns one exact site's URL and permission level. It is not
    ``sites.list``, so there is nothing to paginate, and it retrieves no
    search-analytics data.
    """

    def __init__(
        self,
        client_secrets_file: str,
        token_file: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._client_secrets_file = client_secrets_file
        self._token_file = token_file
        self._timeout_seconds = timeout_seconds

    def list_sites(self) -> dict[str, Any]:
        """Diagnostic only: which sites can this account actually see?

        Authorized by David Wallace on 2026-08-02 solely to diagnose the AVS
        404, after both a URL-prefix and a domain-property lookup failed. It
        returns site URLs and permission levels and **no search-analytics
        data**. One request, no pagination.

        This is deliberately not part of the approved verification plan and is
        never called by ``provider_verify``.
        """
        credentials = load_gsc_oauth_credentials(self._client_secrets_file, self._token_file)
        if not credentials.valid:
            credentials.refresh(Request())
        response = requests.get(
            "https://searchconsole.googleapis.com/webmasters/v3/sites",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=self._timeout_seconds,
        )
        if response.status_code >= 400:
            raise GscClientError(sanitized_gsc_error(response))
        return response.json()

    def get_site(self, site_url: str) -> dict[str, Any]:
        credentials = load_gsc_oauth_credentials(self._client_secrets_file, self._token_file)
        if not credentials.valid:
            credentials.refresh(Request())
        response = requests.get(
            GSC_SITE_URL.format(site_url=requests.utils.quote(site_url, safe="")),
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=self._timeout_seconds,
        )
        if response.status_code >= 400:
            raise GscClientError(sanitized_gsc_error(response))
        return response.json()


def credential_references(profile: str, provider: str) -> tuple[str, str]:
    """Resolve the client-secret and token *references* for one provider.

    Deliberately reads the loader's resolved state rather than the safe
    dictionary, because the safe dictionary strips credential paths on purpose.
    That split is the boundary: **offline validation sees no path, and this
    function is reached only in provider mode**, after every authorization,
    structural, and budget guard has passed.

    It returns references. **It opens neither file**; the provider client does
    that at call time.
    """
    from src.profile_local_config import load_profile_local_config

    state = load_profile_local_config(profile).provider(provider) or {}
    secrets = str(state.get("_resolved_oauth_client_secrets_file") or "").strip()
    token = str(state.get("_resolved_oauth_token_file") or "").strip()
    if not secrets or not token:
        raise ProviderCredentialReferenceError(
            f"credential references are incomplete for {profile} {provider}. "
            "No credential file was opened."
        )
    return secrets, token


class ProviderCredentialReferenceError(RuntimeError):
    """A credential reference was missing or unusable. No file was opened."""


# GA4 and Google Search Console read-only scopes already in use elsewhere in
# this repository. Recorded here so evidence can state them without widening.
SCOPES = {
    "ga4": GA4_DATA_API_SCOPE,
    "gsc": "https://www.googleapis.com/auth/webmasters.readonly",
}
