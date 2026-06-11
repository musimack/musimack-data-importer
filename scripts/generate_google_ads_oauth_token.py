from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
DEFAULT_CLIENT_SECRETS = Path("secrets") / "google-ads" / "client_secrets.local.json"
DEFAULT_TOKEN_OUTPUT = Path("secrets") / "google-ads" / "oauth_token.local.json"


class GoogleAdsOAuthTokenError(ValueError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a local ignored Google Ads OAuth token file without printing token values."
    )
    parser.add_argument("--client-secrets", default=str(DEFAULT_CLIENT_SECRETS), help="Local OAuth client secrets JSON.")
    parser.add_argument("--token-output", default=str(DEFAULT_TOKEN_OUTPUT), help="Ignored local OAuth token JSON output.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing token output file.")
    args = parser.parse_args()

    try:
        generate_google_ads_oauth_token(
            client_secrets_path=Path(args.client_secrets),
            token_output_path=Path(args.token_output),
            overwrite=args.overwrite,
        )
    except GoogleAdsOAuthTokenError as exc:
        print(f"Google Ads OAuth token generation failed safely: {exc}", file=sys.stderr)
        return 1

    print("No token values were printed.")
    return 0


def generate_google_ads_oauth_token(
    *,
    client_secrets_path: Path = DEFAULT_CLIENT_SECRETS,
    token_output_path: Path = DEFAULT_TOKEN_OUTPUT,
    overwrite: bool = False,
) -> Path:
    if not client_secrets_path.exists():
        raise GoogleAdsOAuthTokenError(f"OAuth client secrets file is missing: {client_secrets_path}")
    if token_output_path.exists() and not overwrite:
        raise GoogleAdsOAuthTokenError(f"OAuth token output already exists; pass --overwrite to replace it: {token_output_path}")

    print("OAuth client secrets file found.")
    print("Starting local browser authorization flow.")
    credentials = _run_local_browser_flow(client_secrets_path)
    payload = _token_payload_from_credentials(credentials)
    _write_token_payload(token_output_path, payload)
    print(f"Token file written to {token_output_path}.")
    return token_output_path


def _run_local_browser_flow(client_secrets_path: Path) -> Any:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise GoogleAdsOAuthTokenError(
            "google-auth-oauthlib is not installed; install it locally before generating a token"
        ) from exc
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), scopes=[GOOGLE_ADS_SCOPE])
    return flow.run_local_server(port=0)


def _token_payload_from_credentials(credentials: Any) -> dict[str, Any]:
    refresh_token = str(getattr(credentials, "refresh_token", "") or "").strip()
    if not refresh_token:
        raise GoogleAdsOAuthTokenError("OAuth flow completed but did not return a refresh token")
    payload: dict[str, Any] = {
        "refresh_token": refresh_token,
        "scopes": [GOOGLE_ADS_SCOPE],
    }
    token_uri = str(getattr(credentials, "token_uri", "") or "").strip()
    if token_uri:
        payload["token_uri"] = token_uri
    return payload


def _write_token_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
