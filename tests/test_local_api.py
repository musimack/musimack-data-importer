from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import create_app
from src.operator_console import EXPECTED_DASHBOARD_FILES


def test_health_endpoint_returns_safe_status(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "app": "musimack-data-importer-local-api"}


def test_profiles_endpoint_returns_safe_profile_metadata(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profiles"][0]["slug"] == "demo-profile"
    assert payload["profiles"][0]["display_name"] == "Demo Profile"
    serialized = json.dumps(payload)
    assert "property-123" not in serialized
    assert "secret" not in serialized.lower()


def test_profile_detail_endpoint_includes_readiness_and_outputs_without_contents(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(profile_folder / "ga4-summary.json", {"schema_version": "ga4.v1", "private_metric": "do-not-return"})
    local_config = _local_profile_config(tmp_path)
    client = TestClient(
        create_app(
            registry_path=registry,
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "lf-secret-value",
            },
            local_profile_config_path=local_config,
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["slug"] == "demo-profile"
    assert payload["provider_readiness"][0]["label"] == "GA4"
    assert payload["readiness_matrix"][0]["provider_label"] == "GA4"
    assert payload["provider_setup_checklist"][0]["provider_label"] == "GA4"
    assert payload["output_status"]["files"][1]["file"] == "ga4-summary.json"
    assert payload["output_status"]["files"][1]["schema_version"] == "ga4.v1"
    serialized = json.dumps(payload)
    assert "do-not-return" not in serialized
    assert "property-123" not in serialized
    assert "C:/private" not in serialized
    assert "lf-secret-value" not in serialized


def test_profile_detail_setup_checklist_is_safe_and_profile_scoped(tmp_path):
    registry = _registry(tmp_path)
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    rows = response.json()["provider_setup_checklist"]
    local_falcon = next(item for item in rows if item["provider_key"] == "local_falcon")
    serialized = json.dumps(rows)
    assert local_falcon["profile_slug"] == "demo-profile"
    assert local_falcon["config_state"]["api_key_visible"] is True
    assert "local-falcon-manifests/demo-profile.json" in serialized
    assert "real-api-key-value" not in serialized
    assert "configured_secret_value" not in serialized
    assert "123456789" not in serialized
    assert "https://private-property.example.test/" not in serialized


def test_profile_detail_includes_planned_capabilities_without_fetch_actions(tmp_path):
    registry = _registry(
        tmp_path,
        capabilities=[
            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
            {"key": "google_ads_search", "label": "Google Ads Search", "status": "planned", "kind": "paid_provider"},
            {"key": "callrail", "label": "CallRail", "status": "planned", "kind": "lead_provider"},
        ],
        data_sources=["ga4", "gsc"],
    )
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    payload = response.json()
    ads = next(item for item in payload["readiness_matrix"] if item["provider_key"] == "google_ads_search")
    callrail = next(item for item in payload["readiness_matrix"] if item["provider_key"] == "callrail")
    assert ads["status_label"] == "Planned, not enabled"
    assert ads["live_fetch_status"] == "Not available yet"
    assert callrail["dashboard_copy_readiness"] == "Not available yet"
    checklist_ads = next(item for item in payload["provider_setup_checklist"] if item["provider_key"] == "google_ads_search")
    assert checklist_ads["suggested_command"] == ""
    assert checklist_ads["status"] == "planned"
    assert all(action["provider"] not in {"google_ads_search", "callrail"} for action in payload["action_plan"]["actions"])
    planned = _phase(payload["action_plan"]["guarded_import_sequence"], "planned_capabilities")["providers"]
    assert next(item for item in planned if item["provider"] == "google_ads_search")["command"] == ""
    assert next(item for item in planned if item["provider"] == "callrail")["command"] == ""


def test_profile_detail_includes_current_enabled_provider_files_and_actions(tmp_path):
    registry = _registry(
        tmp_path,
        capabilities=[
            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
            {"key": "local_falcon", "label": "Local Falcon", "status": "enabled", "kind": "importer_provider", "provider": "local_falcon"},
            {"key": "local_falcon_ai", "label": "Local Falcon AI Visibility", "status": "enabled", "kind": "dashboard_room", "notes": "Represented through local-falcon-summary.json"},
            {"key": "google_ads_search", "label": "Google Ads Search", "status": "enabled", "kind": "paid_provider", "provider": "google_ads_search", "expected_output_file": "google-ads-summary.json"},
            {"key": "callrail", "label": "CallRail", "status": "enabled", "kind": "lead_provider", "provider": "callrail", "expected_output_file": "callrail-summary.json"},
            {"key": "form_fills", "label": "Form Fills", "status": "enabled", "kind": "lead_provider", "provider": "form_fills", "expected_output_file": "form-fills-summary.json"},
        ],
        data_sources=["ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills"],
    )
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in (
        "client-profile.json",
        "combined-dashboard-summary.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "local-falcon-summary.json",
        "google-ads-summary.json",
        "callrail-summary.json",
        "form-fills-summary.json",
    ):
        _write_json(source / filename, {"schema_version": f"{filename}.v1", "hidden": "do-not-return"})
    _write_json(source / "ga4-snapshot.json", {"schema_version": "ga4_snapshot.v1", "hidden": "do-not-return"})
    client = TestClient(
        create_app(
            registry_path=registry,
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-secret",
                "GOOGLE_ADS_OAUTH_CLIENT_SECRETS": "C:/private/google-ads-client-secret.json",
                "GOOGLE_ADS_OAUTH_TOKEN_FILE": "C:/private/google-ads-token.json",
                "MUSIMACK_GOOGLE_ADS_CUSTOMER_ID": "9999999999",
                "LOCAL_FALCON_API_KEY": "local-falcon-secret",
            },
            local_profile_config_path=_full_provider_local_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile")
    preview = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 200
    assert preview.status_code == 200
    payload = response.json()
    expected_files = [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
        "local-falcon-summary.json",
        "google-ads-summary.json",
        "callrail-summary.json",
        "form-fills-summary.json",
    ]
    assert payload["output_status"]["expected_files"] == expected_files
    assert [item["file"] for item in preview.json()["items"]] == expected_files
    assert "ga4-snapshot.json" not in payload["output_status"]["expected_files"]
    assert "ga4-snapshot.json" not in [item["file"] for item in preview.json()["items"]]
    assert _action(payload["action_plan"], "google-ads-search-read-only-export")["provider"] == "google_ads_search"
    assert _action(payload["action_plan"], "callrail-csv-import")["provider"] == "callrail"
    assert _action(payload["action_plan"], "form-fills-date-only-import")["provider"] == "form_fills"
    serialized = json.dumps({"profile": payload, "preview": preview.json()})
    assert "do-not-return" not in serialized
    assert "property-123" not in serialized
    assert "9999999999" not in serialized
    assert "developer-token-secret" not in serialized
    assert "local-falcon-secret" not in serialized
    assert "C:/private" not in serialized
    assert "configured_secret_value" not in serialized


def test_unknown_profile_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/missing-profile")

    assert response.status_code == 404


def test_unknown_profile_action_plan_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/missing-profile/action-plan")

    assert response.status_code == 404


def test_unknown_profile_validation_action_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/missing-profile/actions/validate-output")

    assert response.status_code == 404


def test_unknown_profile_copy_preview_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/missing-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 404


def test_unknown_profile_copy_action_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/missing-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 404


def test_action_runs_missing_audit_log_returns_empty_list(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=tmp_path / "logs" / "missing.jsonl"))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    assert response.json() == {"entries": [], "count": 0, "skipped_malformed": 0}


def test_action_runs_endpoint_returns_recent_safe_entries(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(
        audit_path,
        {
            "timestamp": "2026-06-08T10:00:00+00:00",
            "action_id": "validate-output",
            "profile_slug": "demo-profile",
            "status": "ok",
            "result_summary": {"missing_required_file_count": 0, "raw_secret": "secret client payload"},
            "warnings": [],
            "duration_ms": 12,
            "raw_payload": "do-not-return",
        },
    )
    _write_audit(
        audit_path,
        {
            "timestamp": "2026-06-08T10:05:00+00:00",
            "action_id": "copy-to-dashboard-lab",
            "profile_slug": "demo-profile",
            "status": "ok",
            "file_counts": {"copied": 2, "skipped": 1, "failed": 0},
            "warnings": ["skipped missing source file(s): 1"],
            "duration_ms": 15,
        },
    )
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["entries"][0]["action_id"] == "copy-to-dashboard-lab"
    assert payload["entries"][0]["file_counts"]["copied"] == 2
    serialized = json.dumps(payload)
    assert "do-not-return" not in serialized
    assert "secret client payload" not in serialized
    assert "raw_payload" not in serialized


def test_action_runs_limit_and_filters_work(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(audit_path, {"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok"})
    _write_audit(audit_path, {"timestamp": "2", "action_id": "copy-to-dashboard-lab", "profile_slug": "other-profile", "status": "ok"})
    _write_audit(audit_path, {"timestamp": "3", "action_id": "copy-to-dashboard-lab", "profile_slug": "demo-profile", "status": "ok"})
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    limited = client.get("/api/action-runs?limit=1").json()
    filtered = client.get("/api/action-runs?profile_slug=demo-profile&action_id=copy-to-dashboard-lab").json()

    assert limited["count"] == 1
    assert limited["entries"][0]["timestamp"] == "3"
    assert filtered["count"] == 1
    assert filtered["entries"][0]["profile_slug"] == "demo-profile"
    assert filtered["entries"][0]["action_id"] == "copy-to-dashboard-lab"


def test_profile_action_runs_endpoint_filters_by_profile(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(audit_path, {"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok"})
    _write_audit(audit_path, {"timestamp": "2", "action_id": "validate-output", "profile_slug": "other-profile", "status": "ok"})
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/profiles/demo-profile/action-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["entries"][0]["profile_slug"] == "demo-profile"


def test_action_runs_malformed_jsonl_lines_are_skipped(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(
        "\n".join(
            [
                "{bad json",
                json.dumps({"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok"}),
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["skipped_malformed"] == 1


def test_action_runs_does_not_return_secrets(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(
        audit_path,
        {
            "timestamp": "1",
            "action_id": "validate-output",
            "profile_slug": "demo-profile",
            "status": "ok",
            "api_key": "real-api-key-value",
            "refresh_token": "refresh-secret",
            "warnings": ["safe warning"],
        },
    )
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/action-runs")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "real-api-key-value" not in serialized
    assert "refresh-secret" not in serialized
    assert "safe warning" in serialized


def test_profile_detail_includes_last_action_summary_safely(tmp_path):
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    _write_audit(audit_path, {"timestamp": "1", "action_id": "validate-output", "profile_slug": "demo-profile", "status": "ok", "duration_ms": 9})
    _write_audit(audit_path, {"timestamp": "2", "action_id": "copy-to-dashboard-lab", "profile_slug": "demo-profile", "status": "ok", "file_counts": {"copied": 1}})
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}, audit_log_path=audit_path))

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    last_actions = response.json()["last_actions"]
    assert last_actions["last_action"]["action_id"] == "copy-to-dashboard-lab"
    assert last_actions["last_validation"]["action_id"] == "validate-output"
    assert last_actions["last_copy"]["file_counts"]["copied"] == 1


def test_action_runs_unknown_profile_filter_returns_404(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/action-runs?profile_slug=missing-profile")

    assert response.status_code == 404


def test_outputs_endpoint_returns_status_only(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "client_value": "hidden"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/outputs")

    assert response.status_code == 200
    payload = response.json()
    assert [item["file"] for item in payload["files"]] == EXPECTED_DASHBOARD_FILES
    assert payload["files"][0]["exists"] is True
    assert "hidden" not in json.dumps(payload)


def test_local_config_and_secrets_are_not_exposed(tmp_path):
    local_config = _local_profile_config(tmp_path)
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            local_profile_config_path=local_config,
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "123456789" not in serialized
    assert "https://private-property.example.test/" not in serialized
    assert "real-api-key-value" not in serialized
    assert "configured_secret_value" not in serialized
    assert "credentials_ready" in serialized


def test_action_plan_endpoint_returns_safe_structured_data(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "lf-secret-value",
            },
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_slug"] == "demo-profile"
    assert [action["id"] for action in payload["actions"]] == [
        "ga4-snapshot",
        "gsc-fetch",
        "local-falcon-read-only-fetch",
        "validate-local-real-output",
        "copy-to-dashboard-lab-local-fixtures",
    ]
    assert "fetch_gsc_api.py --profile demo-profile" in json.dumps(payload)
    serialized = json.dumps(payload)
    assert "property-123" not in serialized
    assert "C:/private" not in serialized
    assert "lf-secret-value" not in serialized


def test_profile_detail_includes_guarded_import_sequence_without_secret_values(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={
                "MUSIMACK_GA4_PROPERTY_ID": "property-123",
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "lf-secret-value",
            },
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile")

    assert response.status_code == 200
    sequence = response.json()["guarded_import_sequence"]
    fetch_phase = _phase(sequence, "approved_provider_fetches")
    validation_phase = _phase(sequence, "validation_only")
    copy_phase = _phase(sequence, "dashboard_lab_local_copy")
    assert sequence["profile_slug"] == "demo-profile"
    assert fetch_phase["requires_explicit_approval"] is True
    assert fetch_phase["network_allowed"] is True
    assert validation_phase["network_allowed"] is False
    assert copy_phase["network_allowed"] is False
    assert "public/local-fixtures" in copy_phase["destination_folder"].replace("\\", "/")
    assert "public/fixtures" not in copy_phase["destination_folder"].replace("\\", "/")
    serialized = json.dumps(sequence)
    assert "property-123" not in serialized
    assert "C:/private" not in serialized
    assert "lf-secret-value" not in serialized
    assert "configured_secret_value" not in serialized


def test_action_plan_includes_same_guarded_import_sequence(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["guarded_import_sequence"]["profile_slug"] == "demo-profile"
    assert _phase(payload["guarded_import_sequence"], "validation_only")["network_allowed"] is False
    assert [action["id"] for action in payload["actions"]] == [
        "ga4-snapshot",
        "gsc-fetch",
        "local-falcon-read-only-fetch",
        "validate-local-real-output",
        "copy-to-dashboard-lab-local-fixtures",
    ]


def test_ga4_action_blocked_when_property_id_missing(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    action = _action(response.json(), "ga4-snapshot")
    assert action["status"] == "blocked_missing_config"
    assert any("MUSIMACK_GA4_PROPERTY_ID" in item for item in action["missing_inputs"])
    assert "ga4-summary.json writer is available" in " ".join(action["safety_notes"])
    assert action["readiness"]["dashboard_lab_writer_available"] is True


def test_local_falcon_action_checks_api_key_presence_without_exposing_value(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    action = _action(response.json(), "local-falcon-read-only-fetch")
    assert action["readiness"]["api_key_present"] is True
    assert "fetch_local_falcon_api.py" in action["command"]
    serialized = json.dumps(action)
    assert "LOCAL_FALCON_API_KEY" in serialized
    assert "real-api-key-value" not in serialized
    assert "configured_secret_value" not in serialized


def test_copy_action_targets_local_fixtures_not_committed_fixtures(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    action = _action(response.json(), "copy-to-dashboard-lab-local-fixtures")
    assert "public\\local-fixtures" in action["command"] or "public/local-fixtures" in action["command"]
    assert "public\\fixtures" not in action["command"]
    assert "public/fixtures" not in action["command"]
    assert action["readiness"]["destination_is_public_fixtures"] is False


def test_action_plan_does_not_return_raw_file_contents(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(profile_folder / "gsc-summary.json", {"schema_version": "gsc.v1", "raw_query": "secret client query"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    assert "secret client query" not in json.dumps(response.json())


def test_action_plan_avoids_secret_like_values_except_safe_env_var_names(tmp_path):
    client = TestClient(
        create_app(
            registry_path=_registry(tmp_path),
            env={
                "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client-secret.json",
                "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
                "LOCAL_FALCON_API_KEY": "real-api-key-value",
            },
            local_profile_config_path=_local_profile_config(tmp_path),
        )
    )

    response = client.get("/api/profiles/demo-profile/action-plan")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "real-api-key-value" not in serialized
    assert "C:/private" not in serialized
    assert "configured_secret_value" not in serialized
    assert "123456789" not in serialized
    assert "https://private-property.example.test/" not in serialized
    assert "LOCAL_FALCON_API_KEY" in serialized


def test_validation_action_succeeds_with_synthetic_output_folder(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "hidden": "do-not-return"})
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(create_app(registry_path=registry, env={}, audit_log_path=audit_path))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["result"]["folder_exists"] is True
    assert payload["result"]["missing_required_files"] == []
    assert all(item["exists"] for item in payload["result"]["files"])
    assert payload["audit"]["logged"] is True
    assert audit_path.exists()
    assert "do-not-return" not in json.dumps(payload)


def test_validation_action_folder_missing_returns_safe_status(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "folder_missing"
    assert payload["result"]["folder_exists"] is False
    assert "client-profile.json" in payload["result"]["missing_required_files"]


def test_validation_action_reports_missing_files(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(profile_folder / "client-profile.json", {"schema_version": "client.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "missing_outputs"
    assert "ga4-summary.json" in payload["result"]["missing_required_files"]
    assert "combined-dashboard-summary.json" in payload["result"]["missing_required_files"]


def test_validation_action_reports_malformed_json_without_crashing(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1"})
    (profile_folder / "gsc-summary.json").write_text("{bad json", encoding="utf-8")
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid_json"
    assert payload["result"]["malformed_json_files"] == ["gsc-summary.json"]


def test_validation_action_does_not_require_disabled_provider_file(tmp_path):
    registry = _registry(tmp_path, data_sources=["ga4", "gsc"])
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in (
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
    ):
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["result"]["missing_required_files"] == []
    assert payload["result"]["missing_disabled_provider_files"] == ["local-falcon-summary.json"]


def test_generic_action_allowlist_blocks_unsupported_action(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post(
        "/api/actions/run",
        json={"profile_slug": "demo-profile", "action_id": "gsc-fetch"},
    )

    assert response.status_code == 400


def test_generic_action_rejects_arbitrary_path_input(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post(
        "/api/actions/run",
        json={
            "profile_slug": "demo-profile",
            "action_id": "validate-output",
            "path": "C:/not-allowed",
        },
    )

    assert response.status_code == 422


def test_generic_action_can_run_validate_output(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post(
        "/api/actions/run",
        json={"profile_slug": "demo-profile", "action_id": "validate-output"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_validation_action_does_not_return_raw_file_contents(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "raw_value": "secret client payload"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    assert "secret client payload" not in json.dumps(response.json())


def test_validation_audit_log_writes_safe_jsonl_entry(tmp_path):
    registry = _registry(tmp_path)
    profile_folder = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile_folder / filename, {"schema_version": f"{filename}.v1", "raw_value": "secret client payload"})
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            audit_log_path=audit_path,
        )
    )

    response = client.post("/api/profiles/demo-profile/actions/validate-output")

    assert response.status_code == 200
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action_id"] == "validate-output"
    assert entry["profile_slug"] == "demo-profile"
    assert entry["status"] == "ok"
    serialized = json.dumps(entry)
    assert "secret client payload" not in serialized
    assert "real-api-key-value" not in serialized


def test_copy_preview_returns_expected_file_actions(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    destination = tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
    _write_json(source / "client-profile.json", {"schema_version": "client.v1"})
    _write_json(source / "ga4-summary.json", {"schema_version": "ga4.v1"})
    _write_json(destination / "ga4-summary.json", {"schema_version": "old-ga4.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_folder"].endswith("exports\\local-real\\dashboard-lab\\demo-profile") or payload["source_folder"].endswith("exports/local-real/dashboard-lab/demo-profile")
    assert [item["file"] for item in payload["items"]] == EXPECTED_DASHBOARD_FILES
    assert _copy_item(payload, "client-profile.json")["action"] == "copy"
    assert _copy_item(payload, "ga4-summary.json")["action"] == "overwrite"
    assert _copy_item(payload, "gsc-summary.json")["action"] == "skip_missing_source"


def test_copy_action_requires_confirmation(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": False})

    assert response.status_code == 400


def test_copy_action_copies_only_expected_files_and_creates_destination(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    destination = tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(source / filename, {"schema_version": f"{filename}.v1", "payload": "safe"})
    (source / "raw-provider-response.json").write_text('{"raw": true}', encoding="utf-8")
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(create_app(registry_path=registry, env={}, audit_log_path=audit_path))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["counts"]["copied"] == len(EXPECTED_DASHBOARD_FILES)
    assert destination.exists()
    for filename in EXPECTED_DASHBOARD_FILES:
        assert (destination / filename).exists()
    assert not (destination / "raw-provider-response.json").exists()
    assert audit_path.exists()


def test_copy_action_reports_missing_sources_and_overwrites_existing(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    destination = tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
    _write_json(source / "client-profile.json", {"schema_version": "new-client.v1"})
    _write_json(destination / "client-profile.json", {"schema_version": "old-client.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    payload = response.json()
    assert _copy_item(payload, "client-profile.json")["status"] == "overwritten"
    assert _copy_item(payload, "ga4-summary.json")["status"] == "skipped_missing_source"
    assert payload["counts"]["skipped_missing_source"] == 4
    copied_payload = json.loads((destination / "client-profile.json").read_text(encoding="utf-8"))
    assert copied_payload["schema_version"] == "new-client.v1"


def test_copy_destination_committed_fixture_path_is_rejected(tmp_path):
    registry = _registry(tmp_path, local_fixture_folder=tmp_path / "musimack-dashboard-lab" / "public" / "fixtures" / "demo-profile")
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 500


def test_copy_source_outside_local_real_is_rejected(tmp_path):
    registry = _registry(tmp_path, importer_output_folder=tmp_path / "exports" / "not-local-real" / "demo-profile")
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.get("/api/profiles/demo-profile/actions/copy-to-dashboard-lab/preview")

    assert response.status_code == 500


def test_copy_action_rejects_arbitrary_path_input(tmp_path):
    client = TestClient(create_app(registry_path=_registry(tmp_path), env={}))

    response = client.post(
        "/api/profiles/demo-profile/actions/copy-to-dashboard-lab",
        json={"confirmed": True, "destination": "C:/not-allowed"},
    )

    assert response.status_code == 422


def test_generic_action_can_run_copy_to_dashboard_lab(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(source / filename, {"schema_version": f"{filename}.v1"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post(
        "/api/actions/run",
        json={"profile_slug": "demo-profile", "action_id": "copy-to-dashboard-lab", "confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["counts"]["copied"] == len(EXPECTED_DASHBOARD_FILES)


def test_copy_audit_log_writes_safe_jsonl_entry(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(source / filename, {"schema_version": f"{filename}.v1", "raw_value": "secret client payload"})
    audit_path = tmp_path / "logs" / "local-action-runs.jsonl"
    client = TestClient(
        create_app(
            registry_path=registry,
            env={"LOCAL_FALCON_API_KEY": "real-api-key-value"},
            audit_log_path=audit_path,
        )
    )

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    entry = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["action_id"] == "copy-to-dashboard-lab"
    assert entry["file_counts"]["copied"] == len(EXPECTED_DASHBOARD_FILES)
    serialized = json.dumps(entry)
    assert "secret client payload" not in serialized
    assert "real-api-key-value" not in serialized
    assert "raw_value" not in serialized


def test_copy_action_response_does_not_return_file_contents(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    _write_json(source / "client-profile.json", {"schema_version": "client.v1", "raw_value": "secret client payload"})
    client = TestClient(create_app(registry_path=registry, env={}))

    response = client.post("/api/profiles/demo-profile/actions/copy-to-dashboard-lab", json={"confirmed": True})

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "secret client payload" not in serialized
    assert "raw_value" not in serialized


def test_copy_action_does_not_use_shell_or_subprocess():
    text = (Path(__file__).resolve().parents[1] / "server" / "main.py").read_text(encoding="utf-8")

    assert "import subprocess" not in text
    assert "subprocess." not in text
    assert "os.system" not in text
    assert "shell=True" not in text


def _registry(
    tmp_path: Path,
    *,
    data_sources: list[str] | None = None,
    capabilities: list[dict] | None = None,
    importer_output_folder: Path | None = None,
    local_fixture_folder: Path | None = None,
) -> Path:
    registry = tmp_path / "profiles.json"
    registry.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "slug": "demo-profile",
                        "display_name": "Demo Profile",
                        "domain": "demo.example.test",
                        "vertical": "demo",
                        "service_model": "SEO/GEO",
                        "dashboard_lab_route": "/lab/demo-profile",
                        "importer_output_folder": str(importer_output_folder or (
                            tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
                        )),
                        "dashboard_lab_local_fixture_folder": str(local_fixture_folder or (
                            tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile"
                        )),
                        "dashboard_lab_synthetic_fixture_folder": str(
                            tmp_path / "musimack-dashboard-lab" / "public" / "fixtures" / "demo-profile"
                        ),
                        "data_sources": data_sources or ["ga4", "gsc", "local_falcon"],
                        "capabilities": capabilities or [
                            {"key": "ga4", "label": "GA4", "status": "enabled", "kind": "importer_provider", "provider": "ga4"},
                            {"key": "gsc", "label": "GSC", "status": "enabled", "kind": "importer_provider", "provider": "gsc"},
                            {"key": "local_falcon", "label": "Local Falcon", "status": "enabled", "kind": "importer_provider", "provider": "local_falcon"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return registry


def _local_profile_config(tmp_path: Path) -> Path:
    local_config = tmp_path / "dashboard_lab_profiles.local.json"
    local_config.write_text(
        json.dumps(
            {
                "profiles": {
                    "demo-profile": {
                        "providers": {
                            "ga4": {"property_id": "123456789", "credentials_configured": True},
                            "gsc": {"site_url": "https://private-property.example.test/", "credentials_configured": True},
                            "local_falcon": {
                                "manifest_path": str(tmp_path / "private-manifest.json"),
                                "api_key_present": True,
                                "private_note": "configured_secret_value",
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return local_config


def _full_provider_local_config(tmp_path: Path) -> Path:
    local_config = tmp_path / "dashboard_lab_profiles.local.json"
    local_config.write_text(
        json.dumps(
            {
                "profiles": {
                    "demo-profile": {
                        "providers": {
                            "ga4": {"property_id": "123456789", "credentials_configured": True},
                            "gsc": {"site_url": "https://private-property.example.test/", "credentials_configured": True},
                            "local_falcon": {
                                "manifest_path": str(tmp_path / "private-manifest.json"),
                                "api_key_present": True,
                                "private_note": "configured_secret_value",
                            },
                            "google_ads_search": {
                                "customer_id": "9999999999",
                                "credentials_configured": True,
                                "oauth_client_secrets": "C:/private/google-ads-client-secret.json",
                                "oauth_token_file": "C:/private/google-ads-token.json",
                            },
                            "callrail": {
                                "input_csv": str(tmp_path / "private-callrail.csv"),
                            },
                            "form_fills": {
                                "input_csv": str(tmp_path / "private-form-fills.csv"),
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return local_config


def _write_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_audit(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _action(payload: dict, action_id: str) -> dict:
    return next(action for action in payload["actions"] if action["id"] == action_id)


def _copy_item(payload: dict, filename: str) -> dict:
    return next(item for item in payload["items"] if item["file"] == filename)


def _phase(sequence: dict, phase_id: str) -> dict:
    return next(item for item in sequence["phases"] if item["id"] == phase_id)
