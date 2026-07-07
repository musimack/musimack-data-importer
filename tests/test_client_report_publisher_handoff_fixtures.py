import json
import re
from pathlib import Path


FIXTURE_DIR = Path("dev/fixtures/client_report_publisher_handoff")

FORBIDDEN_KEYS = {
    "token",
    "secret",
    "credential",
    "authorization",
    "refresh_token",
    "access_token",
    "client_secret",
    "private_key",
    "service_account",
    "raw_payload",
    "request_body",
    "response_body",
    "config_json",
    "bigquery_project",
    "dataset_id",
    "auto_publish",
}

SECRET_LIKE_VALUE_PATTERNS = [
    re.compile(r"ya29\.", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"bearer\s+[a-z0-9._-]{16,}", re.IGNORECASE),
    re.compile(r"sk-[a-z0-9]{16,}", re.IGNORECASE),
]


def test_client_report_publisher_handoff_fixture_json_files_parse():
    fixture_files = sorted(FIXTURE_DIR.glob("*.json"))

    assert fixture_files
    for fixture_file in fixture_files:
        payload = _load_json(fixture_file)
        assert isinstance(payload, dict)
        assert payload.get("schema_version")


def test_handoff_manifest_references_existing_fixture_files():
    manifest = _load_json(FIXTURE_DIR / "manifest.json")

    referenced_paths = [entry["path"] for entry in manifest["files"]]
    assert referenced_paths
    assert referenced_paths == sorted(referenced_paths)

    for entry in manifest["files"]:
        referenced_file = FIXTURE_DIR / entry["path"]
        assert referenced_file.exists()

        payload = _load_json(referenced_file)
        assert payload["schema_version"] == entry["schema_version"]
        assert payload["provider"] == entry["provider"]
        assert payload["report_type"] == entry["report_type"]


def test_handoff_fixtures_do_not_contain_forbidden_keys_or_secret_values():
    for fixture_file in FIXTURE_DIR.glob("*.json"):
        payload = _load_json(fixture_file)
        flattened = list(_walk(payload))

        for path, value in flattened:
            if path:
                key = path[-1].lower()
                assert key not in FORBIDDEN_KEYS

            if isinstance(value, str):
                lowered = value.lower()
                assert ".env" not in lowered
                assert "oauth" not in lowered
                assert "bigquery" not in lowered
                assert "client-dashboard db" not in lowered
                for pattern in SECRET_LIKE_VALUE_PATTERNS:
                    assert not pattern.search(value)


def test_handoff_fixtures_are_clearly_fake_sample_data():
    for fixture_file in FIXTURE_DIR.glob("*.json"):
        payload = _load_json(fixture_file)

        assert payload.get("client_slug", "sample-client") == "sample-client"
        assert "fake" in payload.get("fixture_notice", "").lower()
        assert "real client data" in payload.get("fixture_notice", "").lower()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield (*path, str(key)), child
            yield from _walk(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, (*path, str(index)))
    else:
        yield path, value
