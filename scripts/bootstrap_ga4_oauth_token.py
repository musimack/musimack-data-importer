from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ga4_client import OAuthCredentialError, load_oauth_credentials
from src.oauth_readiness import build_oauth_readiness_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or refresh the local GA4 OAuth token cache without exporting reports."
    )
    parser.parse_args()

    checks = build_oauth_readiness_report()
    failures = [check for check in checks if check.failed]
    if failures:
        print("GA4 OAuth bootstrap blocked by readiness failures:")
        for check in failures:
            print(check.line())
        print("No token login was attempted.")
        return 1

    client_secrets_file = os.environ["MUSIMACK_GA4_OAUTH_CLIENT_SECRETS"]
    token_file = os.environ["MUSIMACK_GA4_OAUTH_TOKEN_FILE"]
    try:
        credentials = load_oauth_credentials(client_secrets_file, token_file)
    except OAuthCredentialError as exc:
        print(f"GA4 OAuth bootstrap failed safely: {exc}", file=sys.stderr)
        return 1

    if credentials and credentials.valid:
        print("GA4 OAuth bootstrap succeeded; token cache is available. Token contents not printed.")
        return 0
    print("GA4 OAuth bootstrap did not produce valid credentials. Token contents not printed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
