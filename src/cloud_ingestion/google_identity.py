"""Keyless Google service identity tokens for the bounded P2-3D pilot."""

from __future__ import annotations

import urllib.parse
import urllib.request

from .errors import CredentialError


class MetadataIdentityTokenProvider:
    """Obtain one exact-audience ID token from the Cloud Run metadata server."""

    _ENDPOINT = (
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        "service-accounts/default/identity"
    )

    def token_for_audience(self, audience: str) -> str:
        if not audience.startswith("https://") or "*" in audience:
            raise CredentialError("the Portal audience must be an exact https URL")
        query = urllib.parse.urlencode({"audience": audience, "format": "full"})
        request = urllib.request.Request(
            f"{self._ENDPOINT}?{query}",
            headers={"Metadata-Flavor": "Google"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                token = response.read(16 * 1024).decode("ascii").strip()
        except Exception as exc:
            raise CredentialError("Google workload identity was unavailable") from exc
        if not token or len(token) > 16 * 1024 or token.count(".") != 2:
            raise CredentialError("Google workload identity was malformed")
        return token
