"""Explicit per-run authorization for provider-backed reporting profiles.

Governed provider-backed generators previously each carried their own
hard-coded gate of the form ``AUTHORIZED_PROFILE = "aluma-seo-geo"``. That
shape was safe but not extensible: it refused every other governed client
outright, so R8-C5 could not run for the six non-Aluma governed profiles.

This module replaces those gates with one explicit allowlist that must be
supplied for each run. It deliberately does not relax the boundary. It changes
*who decides* from a source constant to an explicit per-run argument, while
keeping every refusal fail-closed.

Design rules, all enforced here rather than in the calling scripts:

- **Default deny.** An omitted or empty allowlist authorizes nothing.
- **No wildcard.** ``*``, ``all``, ``any``, blanks, and whitespace-only entries
  are refused. There is no implicit all-profile mode and no environment-wide
  authorization.
- **Explicit naming only.** Every authorized profile is named in full. Aliases
  resolve, but an entry that resolves to no configured profile is refused.
- **The requested profile must be both configured and authorized.**
- **Authorization runs before anything expensive.** Callers invoke this before
  constructing a provider client and before resolving any credential, so a
  refused run never touches a secret.

Naming only ``aluma-seo-geo`` reproduces the previous effective boundary
exactly, which is how the prior behavior stays available without a special
case.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.profile_aliases import (
    DEFAULT_PROFILE_REGISTRY,
    PROFILE_ALIASES,
    ProfileAliasError,
    load_profile_slugs,
    resolve_profile_slug,
)

AUTHORIZATION_CONTRACT = "musimack_run_profile_authorization.v1"

# Refused outright, before slug resolution, so that no spelling of "everything"
# can ever authorize a run. These are checked case-insensitively.
WILDCARD_TOKENS = frozenset({"*", "all", "any", "everything", "-", "_"})

AUTHORIZED_PROFILE_ARGUMENT = "--authorized-profile"

_ARGUMENT_HELP = (
    "Authorize exactly one reporting profile for this run. Repeat the option "
    "once per profile. There is no default and no wildcard: a run with no "
    "--authorized-profile is refused before any credential is read."
)


class ProfileAuthorizationError(ValueError):
    """A run was refused. Raised before any credential or provider access."""


@dataclass(frozen=True)
class ProfileAuthorization:
    """The result of a successful authorization, recorded in run evidence."""

    requested_profile: str
    authorized_profiles: tuple[str, ...]
    contract: str = AUTHORIZATION_CONTRACT

    def evidence(self) -> dict[str, object]:
        """Sanitized evidence describing what this run was allowed to do.

        Contains no credential value, no credential path, no token, and no
        provider identifier. ``provider_calls_started`` is false here because
        authorization completes before any provider client is constructed.
        """
        return {
            "authorization_contract": self.contract,
            "requested_profile": self.requested_profile,
            "authorized_profiles": list(self.authorized_profiles),
            "authorization_result": "authorized",
            "credential_access_started": False,
            "provider_client_construction_started": False,
        }


def add_authorized_profile_argument(parser) -> None:
    """Register the repeatable ``--authorized-profile`` option on a parser."""
    parser.add_argument(
        AUTHORIZED_PROFILE_ARGUMENT,
        action="append",
        dest="authorized_profiles",
        default=None,
        metavar="PROFILE",
        help=_ARGUMENT_HELP,
    )


def authorize_profile(
    requested_profile: str,
    authorized_entries: Sequence[str] | None,
    *,
    registry_path: Path = DEFAULT_PROFILE_REGISTRY,
    aliases: Mapping[str, str] = PROFILE_ALIASES,
) -> ProfileAuthorization:
    """Authorize one requested profile against an explicit per-run allowlist.

    Returns a :class:`ProfileAuthorization` on success. Raises
    :class:`ProfileAuthorizationError` on every refusal.

    Must be called before constructing a provider client and before resolving
    any credential.
    """
    configured = load_profile_slugs(registry_path)

    if authorized_entries is None:
        raise ProfileAuthorizationError(
            "no reporting profile is authorized for this run: pass "
            f"{AUTHORIZED_PROFILE_ARGUMENT} once per profile. There is no "
            "default and no wildcard. No credential was read and no provider "
            "client was constructed."
        )
    if len(authorized_entries) == 0:
        raise ProfileAuthorizationError(
            "the authorized profile list is empty, which authorizes nothing. "
            "No credential was read and no provider client was constructed."
        )

    authorized: set[str] = set()
    for entry in authorized_entries:
        authorized.add(_resolve_authorized_entry(entry, configured, registry_path, aliases))

    resolved_request = _resolve_requested_profile(requested_profile, configured, registry_path, aliases)

    if resolved_request not in authorized:
        raise ProfileAuthorizationError(
            f"profile {resolved_request} is not authorized for this run. "
            f"Authorized: {', '.join(sorted(authorized))}. "
            "No credential was read and no provider client was constructed."
        )

    # Duplicates collapse deterministically and ordering is sorted, so the same
    # allowlist always produces byte-identical evidence regardless of argument
    # order or repetition.
    return ProfileAuthorization(
        requested_profile=resolved_request,
        authorized_profiles=tuple(sorted(authorized)),
    )


def refusal_evidence(requested_profile: str, reason: str) -> dict[str, object]:
    """Sanitized evidence for a refused run.

    Never implies a successful provider run. Carries no credential value or
    path. The requested profile is echoed verbatim and untrusted, so it is
    recorded as a raw string rather than resolved.
    """
    return {
        "authorization_contract": AUTHORIZATION_CONTRACT,
        "requested_profile": str(requested_profile),
        "authorized_profiles": [],
        "authorization_result": "refused",
        "refusal_reason": reason,
        "credential_access_started": False,
        "provider_client_construction_started": False,
        "provider_calls": 0,
    }


def _resolve_authorized_entry(
    entry: object,
    configured: Iterable[str],
    registry_path: Path,
    aliases: Mapping[str, str],
) -> str:
    if not isinstance(entry, str) or not entry.strip():
        raise ProfileAuthorizationError(
            "an authorized profile entry was blank or whitespace-only, which "
            "authorizes nothing. Name each profile explicitly."
        )
    if entry.strip().lower() in WILDCARD_TOKENS:
        raise ProfileAuthorizationError(
            f"wildcard authorization is not supported: {entry.strip()!r} is refused. "
            "Name every authorized profile explicitly."
        )
    try:
        resolved = resolve_profile_slug(entry, registry_path=registry_path, aliases=aliases)
    except ProfileAliasError as exc:
        raise ProfileAuthorizationError(
            f"authorized profile entry {entry.strip()!r} is not a valid profile slug: {exc}"
        ) from exc
    if resolved not in configured:
        raise ProfileAuthorizationError(
            f"authorized profile {resolved} is not a configured reporting profile. "
            "An unknown profile cannot be authorized."
        )
    return resolved


def _resolve_requested_profile(
    requested_profile: str,
    configured: Iterable[str],
    registry_path: Path,
    aliases: Mapping[str, str],
) -> str:
    try:
        resolved = resolve_profile_slug(requested_profile, registry_path=registry_path, aliases=aliases)
    except ProfileAliasError as exc:
        raise ProfileAuthorizationError(
            f"requested profile {str(requested_profile).strip()!r} is not a valid profile slug: {exc}"
        ) from exc
    if resolved not in configured:
        raise ProfileAuthorizationError(
            f"requested profile {resolved} is not a configured reporting profile."
        )
    return resolved
