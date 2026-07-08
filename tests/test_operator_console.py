import json
from pathlib import Path

import pytest

from src.operator_console import (
    DashboardLabProfile,
    EXPECTED_DASHBOARD_FILES,
    OperatorConsoleError,
    command_guidance,
    copy_dry_run,
    copy_guidance,
    copy_local_real_to_dashboard_lab,
    expected_dashboard_files,
    guarded_import_sequence,
    load_dashboard_lab_profiles,
    output_folder_status,
    profile_by_slug,
    provider_readiness,
    provider_setup_checklist,
    readiness_matrix,
    validate_profile_output,
)
from src.profile_registry_writer import (
    ProfileRegistryWriteError,
    build_profile_registry_draft,
    preview_profile_registry_update,
    write_profile_registry_update,
)


def test_dashboard_lab_profile_registry_loads_safe_profiles():
    profiles = load_dashboard_lab_profiles()
    slugs = [profile.slug for profile in profiles]

    assert "aluma-seo-geo" in slugs
    assert "inn-at-spanish-head" in slugs
    assert "lucy-escobar" in slugs
    assert "pinnacle-contractors" in slugs
    assert "western-wood-structures" in slugs
    assert "avs" in slugs
    assert "musimack-marketing" in slugs
    assert "wc-land-renewal" in slugs
    assert "steadfast-decks-and-fences" in slugs
    assert "steadfast-decks" not in slugs
    assert "portland-tattoo-co" in slugs
    inn = profile_by_slug("inn-at-spanish-head", profiles)
    assert inn.display_name == "Spanish Head"
    assert inn.domain == "spanishhead.com"
    assert inn.data_sources == ["ga4", "gsc", "local_falcon"]
    assert "Alpha priority" in inn.service_model
    assert inn.importer_output_folder.as_posix().endswith("exports/local-real/dashboard-lab/inn-at-spanish-head")
    assert "public/local-fixtures/inn-at-spanish-head" in inn.dashboard_lab_local_fixture_folder.as_posix()
    assert "public/fixtures/inn-at-spanish-head" in inn.dashboard_lab_synthetic_fixture_folder.as_posix()
    assert _capability(inn, "google_ads_search").status == "planned"
    assert _capability(inn, "google_ads_search").expected_output_file == "google-ads-search-summary.json"
    lucy = profile_by_slug("lucy-escobar", profiles)
    pinnacle = profile_by_slug("pinnacle-contractors", profiles)
    western = profile_by_slug("western-wood-structures", profiles)
    avs = profile_by_slug("avs", profiles)
    musimack = profile_by_slug("musimack-marketing", profiles)
    wc = profile_by_slug("wc-land-renewal", profiles)
    steadfast = profile_by_slug("steadfast-decks-and-fences", profiles)
    tattoo = profile_by_slug("portland-tattoo-co", profiles)
    assert lucy.domain == "lucyescobar.com"
    assert lucy.data_sources == ["ga4", "gsc"]
    assert pinnacle.domain == "pinnaclecontractorsllc.com"
    assert pinnacle.data_sources == ["ga4", "gsc", "local_falcon"]
    assert western.display_name == "Western Wood Structures"
    assert western.domain == "westernwoodstructures.com"
    assert western.data_sources == ["ga4", "gsc"]
    assert _capability(western, "local_falcon").status == "planned"
    assert avs.display_name == "AVS"
    assert avs.domain == "avs.example.invalid"
    assert avs.data_sources == []
    assert musimack.domain == "musimackmarketing.com"
    assert musimack.data_sources == ["ga4", "gsc", "local_falcon"]
    assert wc.display_name == "WC Land Renewal"
    assert wc.data_sources == ["ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills"]
    assert _capability(wc, "google_ads_search").status == "enabled"
    assert _capability(wc, "google_ads_search").expected_output_file == "google-ads-summary.json"
    assert _capability(wc, "callrail").status == "enabled"
    assert _capability(wc, "callrail").expected_output_file == "callrail-summary.json"
    assert expected_dashboard_files(wc) == [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
        "local-falcon-summary.json",
        "google-ads-summary.json",
        "callrail-summary.json",
        "form-fills-summary.json",
    ]
    assert steadfast.display_name == "Steadfast Decks and Fences"
    assert steadfast.domain == "steadfastdecks.com"
    assert steadfast.data_sources == ["ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills"]
    assert steadfast.importer_output_folder.as_posix().endswith("exports/local-real/dashboard-lab/steadfast-decks-and-fences")
    assert _capability(steadfast, "google_ads_search").status == "enabled"
    assert _capability(steadfast, "google_ads_search").expected_output_file == "google-ads-summary.json"
    assert _capability(steadfast, "callrail").status == "enabled"
    assert _capability(steadfast, "callrail").expected_output_file == "callrail-summary.json"
    assert _capability(steadfast, "form_fills").status == "enabled"
    assert _capability(steadfast, "form_fills").expected_output_file == "form-fills-summary.json"
    assert tattoo.importer_output_folder.as_posix().endswith("exports/local-real/dashboard-lab/portland-tattoo-co")
    assert {profile.domain for profile in profiles} >= {
        "alumapdx.com",
        "spanishhead.com",
        "lucyescobar.com",
        "pinnaclecontractorsllc.com",
        "westernwoodstructures.com",
        "avs.example.invalid",
        "musimackmarketing.com",
        "wclandrenewal.com",
        "steadfastdecks.com",
        "portlandtattooco.com",
    }
    assert _capability(pinnacle, "google_ads_search").status == "planned"
    assert _capability(pinnacle, "google_lsa").status == "planned"
    assert _capability(pinnacle, "callrail").status == "planned"
    assert _capability(lucy, "local_falcon").status == "planned"


def test_registry_rejects_local_fixture_path_pointing_to_committed_fixtures(tmp_path):
    registry = tmp_path / "profiles.json"
    registry.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "slug": "unsafe-profile",
                        "display_name": "Unsafe",
                        "domain": "example.com",
                        "vertical": "demo",
                        "service_model": "demo",
                        "dashboard_lab_route": "/lab/unsafe-profile",
                        "importer_output_folder": "exports/local-real/dashboard-lab/unsafe-profile",
                        "dashboard_lab_local_fixture_folder": "../musimack-dashboard-lab/public/fixtures/unsafe-profile",
                        "dashboard_lab_synthetic_fixture_folder": "../musimack-dashboard-lab/public/fixtures/unsafe-profile",
                        "data_sources": ["ga4"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(OperatorConsoleError, match="public/fixtures"):
        load_dashboard_lab_profiles(registry)


def test_profile_registry_writer_builds_safe_draft():
    draft = build_profile_registry_draft()

    assert "ga4" in draft["draft"]["data_sources"]
    assert "local_falcon" in draft["draft"]["data_sources"]
    assert any(item["key"] == "content" for item in draft["capability_options"])
    assert any(item["key"] == "google_ads_search" for item in draft["provider_options"])
    assert "Do not enter secrets" in draft["warnings"][0]


def test_profile_registry_writer_preview_generates_paths_without_writing(tmp_path):
    registry = _registry(tmp_path)
    preview = preview_profile_registry_update(
        {
            "slug": "new-client",
            "display_name": "New Client",
            "domain": "example.com",
            "vertical": "local service",
            "service_model": "SEO/GEO",
            "data_sources": ["ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills"],
            "capabilities": [
                {"key": "content", "status": "enabled"},
                {"key": "strategy", "status": "enabled"},
                {"key": "reports", "status": "enabled"},
                {"key": "support", "status": "enabled"},
                {"key": "operator_profile", "status": "enabled"},
                {"key": "local_falcon_ai", "status": "planned"},
            ],
        },
        registry_path=registry,
    )

    payload = preview.as_safe_dict()
    assert preview.blocked is False
    assert payload["profile"]["dashboard_lab_route"] == "/lab/new-client"
    assert payload["profile"]["importer_output_folder"] == "exports/local-real/dashboard-lab/new-client"
    assert payload["profile"]["dashboard_lab_local_fixture_folder"] == "../musimack-dashboard-lab/public/local-fixtures/new-client"
    assert "google-ads-summary.json" in payload["expected_files"]
    assert "callrail-summary.json" in payload["expected_files"]
    assert "form-fills-summary.json" in payload["expected_files"]
    assert "ga4-snapshot.json" not in payload["expected_files"]
    assert "new-client" not in [profile.slug for profile in load_dashboard_lab_profiles(registry)]


def test_profile_registry_writer_rejects_duplicate_invalid_unknown_and_secret_like_values(tmp_path):
    registry = _registry(tmp_path)
    preview = preview_profile_registry_update(
        {
            "slug": "demo-profile",
            "display_name": '{"client_secret":"value"}',
            "domain": "example.com",
            "vertical": "local service",
            "service_model": "SEO/GEO",
            "data_sources": ["ga4", "unknown_provider"],
            "capabilities": [{"key": "unknown_capability", "status": "enabled"}],
            "importer_output_folder": "C:/not-allowed",
        },
        registry_path=registry,
    )

    serialized = json.dumps(preview.as_safe_dict())
    assert preview.blocked is True
    assert "slug already exists" in serialized
    assert "not allowed" in serialized
    assert "not editable" in serialized
    assert '{"client_secret":"value"}' not in serialized
    assert "C:/not-allowed" not in serialized


def test_profile_registry_writer_rejects_invalid_capability_status(tmp_path):
    registry = _registry(tmp_path)
    preview = preview_profile_registry_update(
        {
            "slug": "new-client",
            "display_name": "New Client",
            "domain": "example.com",
            "vertical": "local service",
            "service_model": "SEO/GEO",
            "data_sources": ["ga4"],
            "capabilities": [{"key": "content", "status": "active"}],
        },
        registry_path=registry,
    )

    assert preview.blocked is True
    assert "capability status must be enabled or planned" in json.dumps(preview.as_safe_dict())


def test_profile_registry_writer_save_requires_confirmation_and_preserves_order(tmp_path):
    registry = _registry(tmp_path)
    draft = {
        "slug": "new-client",
        "display_name": "New Client",
        "domain": "example.com",
        "vertical": "local service",
        "service_model": "SEO/GEO",
        "data_sources": ["ga4", "gsc"],
        "capabilities": [
            {"key": "content", "status": "enabled"},
            {"key": "strategy", "status": "enabled"},
            {"key": "reports", "status": "enabled"},
            {"key": "support", "status": "enabled"},
            {"key": "operator_profile", "status": "enabled"},
        ],
    }

    with pytest.raises(ProfileRegistryWriteError):
        write_profile_registry_update(draft, confirmed=False, registry_path=registry)

    response = write_profile_registry_update(draft, confirmed=True, registry_path=registry)
    profiles = load_dashboard_lab_profiles(registry)

    assert response["saved"] is True
    assert [profile.slug for profile in profiles] == ["demo-profile", "new-client"]
    new_profile = profile_by_slug("new-client", profiles)
    assert new_profile.dashboard_lab_route == "/lab/new-client"
    assert expected_dashboard_files(new_profile)


def test_provider_readiness_reports_safe_presence_without_values():
    profile = profile_by_slug("inn-at-spanish-head")
    rows = provider_readiness(
        profile,
        env={
            "MUSIMACK_GA4_PROPERTY_ID": "123456",
            "MUSIMACK_GA4_AUTH_METHOD": "oauth",
            "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/secret/client.json",
            "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/secret/token.json",
            "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/secret/client.json",
            "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/secret/gsc-token.json",
            "LOCAL_FALCON_API_KEY": "lf-secret",
        },
        local_config={},
    )

    assert {"provider": "GA4", "status": "configured", "detail": "auth=oauth; property id present"} in rows
    assert any(row["provider"] == "GSC" and row["status"] == "configured" for row in rows)
    serialized = json.dumps(rows)
    assert "lf-secret" not in serialized
    assert "C:/secret" not in serialized


def test_output_folder_status_reports_schema_without_contents(tmp_path):
    profile = profile_by_slug("inn-at-spanish-head")
    local_profile = profile.__class__(
        **{**profile.__dict__, "importer_output_folder": tmp_path}
    )
    (tmp_path / "ga4-summary.json").write_text(
        json.dumps({"schema_version": "dashboard_lab_provider_summary.v1", "real_value": "do-not-display"}),
        encoding="utf-8",
    )

    rows = output_folder_status(local_profile)
    ga4 = next(row for row in rows if row["file"] == "ga4-summary.json")

    assert [row["file"] for row in rows] == EXPECTED_DASHBOARD_FILES
    assert ga4["exists"] == "yes"
    assert ga4["schema_version"] == "dashboard_lab_provider_summary.v1"
    assert "do-not-display" not in json.dumps(rows)


def test_command_and_copy_guidance_stay_on_ignored_local_paths():
    profile = profile_by_slug("inn-at-spanish-head")
    commands = command_guidance(profile)
    copy = copy_guidance(profile)

    assert any("fetch_gsc_api.py --profile inn-at-spanish-head" in item["command"] for item in commands)
    assert any("sc-domain:spanishhead.com" in item["command"] for item in commands)
    assert any("pull_ga4_traffic_overview.py" in item["command"] for item in commands)
    assert any("write_ga4_dashboard_lab_summary.py --profile inn-at-spanish-head" in item["command"] for item in commands)
    assert any("fetch_local_falcon_api.py" in item["command"] for item in commands)
    assert "exports\\local-real" in copy or "exports/local-real" in copy
    assert "public\\local-fixtures" in copy or "public/local-fixtures" in copy
    assert "public\\fixtures" not in copy and "public/fixtures" not in copy


def test_guarded_import_sequence_for_spanish_head_is_approval_gated_and_profile_scoped():
    profile = profile_by_slug("inn-at-spanish-head")

    sequence = guarded_import_sequence(profile)
    serialized = json.dumps(sequence)
    fetch_phase = _phase(sequence, "approved_provider_fetches")
    validation_phase = _phase(sequence, "validation_only")
    copy_phase = _phase(sequence, "dashboard_lab_local_copy")
    planned_phase = _phase(sequence, "planned_capabilities")

    assert sequence["profile_slug"] == "inn-at-spanish-head"
    assert sequence["domain"] == "spanishhead.com"
    assert sequence["local_real_output_folder"].endswith("exports\\local-real\\dashboard-lab\\inn-at-spanish-head") or sequence[
        "local_real_output_folder"
    ].endswith("exports/local-real/dashboard-lab/inn-at-spanish-head")
    assert fetch_phase["requires_explicit_approval"] is True
    assert fetch_phase["network_allowed"] is True
    assert validation_phase["network_allowed"] is False
    assert copy_phase["network_allowed"] is False
    assert "public/local-fixtures" in copy_phase["destination_folder"].replace("\\", "/")
    assert "/public/fixtures/" not in copy_phase["destination_folder"].replace("\\", "/")
    assert "exports/local-real/dashboard-lab/aluma-seo-geo" not in serialized.replace("\\", "/")
    assert "client_secret" not in serialized.lower()

    providers = {item["provider"]: item for item in fetch_phase["providers"]}
    assert set(providers) == {"ga4", "gsc", "local_falcon"}
    assert all(item["requires_explicit_approval"] for item in providers.values())
    assert "fetch_gsc_api.py --profile inn-at-spanish-head" in providers["gsc"]["command"]
    assert "--transport live" in providers["local_falcon"]["command"]
    assert "--execute --write" in providers["local_falcon"]["command"]

    planned_ads = next(item for item in planned_phase["providers"] if item["provider"] == "google_ads_search")
    assert planned_ads["command"] == ""
    assert planned_ads["writes_real_output"] is False
    assert "do not create fake real output" in planned_ads["guardrails"]


def test_readiness_matrix_reports_missing_output_as_planning_state(tmp_path):
    profile = _test_profile(tmp_path, source_exists=False)

    rows = readiness_matrix(profile, env={})
    ga4 = _matrix_row(rows, "ga4")

    assert ga4["local_output_status"] == "No local output yet"
    assert ga4["validate_readiness"] == "Blocked until output exists"
    assert ga4["dashboard_copy_readiness"] == "Blocked until output exists"
    assert ga4["status_label"] == "Live fetch needs config"
    assert ga4["status_severity"] == "warning"


def test_readiness_matrix_reports_existing_aluma_style_output(tmp_path):
    profile = _test_profile(tmp_path)
    _write_json(profile.importer_output_folder / "local-falcon-summary.json", "local-falcon-summary.json")

    rows = readiness_matrix(profile, env={"LOCAL_FALCON_API_KEY": "do-not-display"})
    local_falcon = _matrix_row(rows, "local_falcon")
    serialized = json.dumps(rows)

    assert local_falcon["local_output_status"] == "Output exists"
    assert local_falcon["validate_readiness"] == "Ready"
    assert local_falcon["dashboard_copy_readiness"] == "Ready"
    assert local_falcon["status_label"] == "Ready to copy"
    assert "do-not-display" not in serialized


def test_planned_future_providers_do_not_create_active_fetch_state():
    profile = profile_by_slug("pinnacle-contractors")

    rows = readiness_matrix(profile, env={})
    ads = _matrix_row(rows, "google_ads_search")
    lsa = _matrix_row(rows, "google_lsa")
    callrail = _matrix_row(rows, "callrail")

    assert ads["capability_status"] == "planned"
    assert ads["live_fetch_status"] == "Not available yet"
    assert ads["validate_readiness"] == "Not available yet"
    assert lsa["status_label"] == "Planned, not enabled"
    assert callrail["dashboard_copy_readiness"] == "Not available yet"


def test_paid_lead_gen_rooms_are_capability_gated():
    aluma = profile_by_slug("aluma-seo-geo")
    pinnacle = profile_by_slug("pinnacle-contractors")

    assert _capability(pinnacle, "google_ads_search").status == "planned"
    assert _capability(pinnacle, "google_lsa").status == "planned"
    assert _capability(pinnacle, "callrail").status == "planned"
    assert not any(item.key in {"google_ads_search", "google_lsa", "callrail", "leads"} for item in aluma.capabilities)


def test_registry_paths_are_profile_scoped_and_do_not_cross_copy_from_aluma():
    profiles = load_dashboard_lab_profiles()

    for profile in profiles:
        source = profile.importer_output_folder.as_posix()
        destination = profile.dashboard_lab_local_fixture_folder.as_posix()
        assert source.endswith(f"exports/local-real/dashboard-lab/{profile.slug}")
        assert destination.endswith(f"public/local-fixtures/{profile.slug}")
        if profile.slug != "aluma-seo-geo":
            assert "aluma-seo-geo" not in source
            assert "aluma-seo-geo" not in destination


def test_provider_setup_checklist_exists_for_all_configured_profiles():
    profiles = load_dashboard_lab_profiles()

    for profile in profiles:
        rows = provider_setup_checklist(profile, env={})
        assert rows
        assert all(row["profile_slug"] == profile.slug for row in rows)
        assert all(row["domain"] == profile.domain for row in rows)


def test_provider_setup_checklist_reports_missing_local_output_without_error(tmp_path):
    profile = _test_profile(tmp_path, source_exists=False)

    rows = provider_setup_checklist(profile, env={})
    ga4 = _matrix_row(rows, "ga4")

    assert ga4["local_output_state"] == "No local output yet"
    assert ga4["status"] == "needs_config"
    assert ga4["safe_next_action"] == "GA4 writer ready; add missing local property/auth config before snapshot export."
    assert "Needs config" in ga4["blocked_reason"]


def test_provider_setup_checklist_supported_provider_config_checks_are_safe(tmp_path):
    profile = _test_profile(tmp_path)
    rows = provider_setup_checklist(
        profile,
        env={
            "MUSIMACK_GA4_PROPERTY_ID": "property-secret",
            "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": "C:/private/client.json",
            "MUSIMACK_GA4_OAUTH_TOKEN_FILE": "C:/private/token.json",
            "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS": "C:/private/client.json",
            "MUSIMACK_GSC_OAUTH_TOKEN_FILE": "C:/private/gsc-token.json",
            "LOCAL_FALCON_API_KEY": "lf-secret-value",
        },
        local_config={
            "providers": {
                "gsc": {"site_url": "https://private.example.test/"},
                "local_falcon": {"local_falcon_manifest_configured": True},
            }
        },
    )

    ga4 = _matrix_row(rows, "ga4")
    gsc = _matrix_row(rows, "gsc")
    local_falcon = _matrix_row(rows, "local_falcon")
    serialized = json.dumps(rows)

    assert ga4["config_state"] == {"property_id_configured": True, "auth_configured": True}
    assert gsc["config_state"] == {"site_url_configured": True, "oauth_configured": True}
    assert local_falcon["config_state"]["api_key_visible"] is True
    assert local_falcon["config_state"]["manifest_exists"] is True
    assert "lf-secret-value" not in serialized
    assert "property-secret" not in serialized
    assert "C:/private" not in serialized
    assert "https://private.example.test/" not in serialized


def test_provider_setup_checklist_uses_profile_local_config_when_present(tmp_path):
    client = tmp_path / "client.json"
    token = tmp_path / "token.json"
    manifest = tmp_path / "inn-at-spanish-head-manifest.json"
    client.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    manifest.write_text("{}", encoding="utf-8")
    config_dir = tmp_path / "local-profile-configs"
    config_dir.mkdir()
    (config_dir / "inn-at-spanish-head.local.json").write_text(
        json.dumps(
            {
                "profile": "inn-at-spanish-head",
                "ga4": {
                    "property_id_env": "INN_GA4_PROPERTY_ID",
                    "oauth_client_secrets_env": "INN_GA4_CLIENT",
                    "oauth_token_file_env": "INN_GA4_TOKEN",
                },
                "gsc": {
                    "site_url": "https://spanishhead.com/",
                    "oauth_client_secrets_env": "INN_GSC_CLIENT",
                    "oauth_token_file_env": "INN_GSC_TOKEN",
                },
                "local_falcon": {
                    "manifest_path": str(manifest),
                    "api_key_env": "INN_LOCAL_FALCON_API_KEY",
                },
                "google_ads_search": {"status": "planned"},
            }
        ),
        encoding="utf-8",
    )
    profile = profile_by_slug("inn-at-spanish-head")

    rows = provider_setup_checklist(
        profile,
        env={
            "INN_GA4_PROPERTY_ID": "secret-property-id",
            "INN_GA4_CLIENT": str(client),
            "INN_GA4_TOKEN": str(token),
            "INN_GSC_CLIENT": str(client),
            "INN_GSC_TOKEN": str(token),
            "INN_LOCAL_FALCON_API_KEY": "secret-api-key",
        },
        local_config_dir=config_dir,
    )

    ga4 = _matrix_row(rows, "ga4")
    gsc = _matrix_row(rows, "gsc")
    local_falcon = _matrix_row(rows, "local_falcon")
    serialized = json.dumps(rows)
    assert ga4["local_config_file_present"] is True
    assert ga4["local_config_path_label"].endswith("inn-at-spanish-head.local.json")
    assert ga4["config_state"]["property_id_configured"] is True
    assert ga4["config_state"]["auth_configured"] is True
    assert ga4["config_state"]["oauth_client_file_exists"] is True
    assert gsc["config_state"]["site_url_configured"] is True
    assert local_falcon["config_state"]["manifest_exists"] is True
    assert local_falcon["config_state"]["api_key_visible"] is True
    assert "secret-property-id" not in serialized
    assert "secret-api-key" not in serialized
    assert str(client) not in serialized
    assert str(token) not in serialized


def test_profile_local_config_does_not_cross_profiles(tmp_path):
    config_dir = tmp_path / "local-profile-configs"
    config_dir.mkdir()
    (config_dir / "aluma-seo-geo.local.json").write_text(
        json.dumps(
            {
                "profile": "aluma-seo-geo",
                "ga4": {"property_id_env": "ALUMA_GA4_PROPERTY_ID"},
            }
        ),
        encoding="utf-8",
    )
    profile = profile_by_slug("inn-at-spanish-head")

    rows = provider_setup_checklist(
        profile,
        env={"ALUMA_GA4_PROPERTY_ID": "secret-aluma-property"},
        local_config_dir=config_dir,
    )

    ga4 = _matrix_row(rows, "ga4")
    serialized = json.dumps(rows)
    assert ga4["local_config_file_present"] is False
    assert ga4["config_state"]["property_id_configured"] is False
    assert "aluma-seo-geo.local.json" not in serialized
    assert "secret-aluma-property" not in serialized


def test_provider_setup_checklist_planned_providers_have_no_active_fetch_commands():
    profile = profile_by_slug("pinnacle-contractors")

    rows = provider_setup_checklist(profile, env={})
    ads = _matrix_row(rows, "google_ads_search")
    callrail = _matrix_row(rows, "callrail")

    assert ads["status"] == "planned"
    assert ads["suggested_command"] == ""
    assert "still planned for this profile" in ads["safe_next_action"]
    assert callrail["suggested_command"] == ""


def test_provider_setup_checklist_commands_are_profile_scoped_and_redacted(tmp_path):
    profile = _test_profile(tmp_path)
    rows = provider_setup_checklist(profile, env={"LOCAL_FALCON_API_KEY": "lf-secret-value"})
    serialized = json.dumps(rows)

    assert "lf-secret-value" not in serialized
    assert "local-falcon-manifests/demo-profile.json" in serialized
    assert "exports/local-real/dashboard-lab/demo-profile/local-falcon-summary.json" in serialized
    assert "exports/local-real/dashboard-lab/aluma-seo-geo" not in serialized


def test_provider_setup_checklist_aluma_style_existing_output_is_usable(tmp_path):
    profile = _test_profile(tmp_path)
    _write_json(profile.importer_output_folder / "local-falcon-summary.json", "local-falcon-summary.json")

    rows = provider_setup_checklist(
        profile,
        env={"LOCAL_FALCON_API_KEY": "lf-secret-value"},
        local_config={"providers": {"local_falcon": {"local_falcon_manifest_configured": True}}},
    )
    local_falcon = _matrix_row(rows, "local_falcon")

    assert local_falcon["local_output_state"] == "Output exists"
    assert local_falcon["status"] == "ready"
    assert "Refresh provider output" in local_falcon["safe_next_action"]


def test_spanish_head_alpha_readiness_is_profile_scoped_and_ads_planned(tmp_path):
    inn = profile_by_slug("inn-at-spanish-head")
    local_inn = inn.__class__(
        **{
            **inn.__dict__,
            "importer_output_folder": tmp_path / "exports" / "local-real" / "dashboard-lab" / "inn-at-spanish-head",
        }
    )

    rows = provider_setup_checklist(local_inn, env={})
    ga4 = _matrix_row(rows, "ga4")
    gsc = _matrix_row(rows, "gsc")
    local_falcon = _matrix_row(rows, "local_falcon")
    ads = _matrix_row(rows, "google_ads_search")
    serialized = json.dumps(rows)

    assert ga4["local_output_state"] == "No local output yet"
    assert "GA4 property id" in ga4["required_config_items"]
    assert ga4["dashboard_lab_writer_status"] == "Ready"
    assert "GA4 writer ready" in ga4["safe_next_action"]
    assert "write_ga4_dashboard_lab_summary.py --profile inn-at-spanish-head" in ga4["suggested_command"]
    assert gsc["local_output_state"] == "No local output yet"
    assert "GSC site URL" in gsc["required_config_items"]
    assert local_falcon["local_output_state"] == "No local output yet"
    assert "ignored Local Falcon manifest" in local_falcon["required_config_items"]
    assert ads["status"] == "planned"
    assert ads["expected_output_file"] == "google-ads-search-summary.json"
    assert ads["output_exists"] is False
    assert ads["config_visible"] is False
    assert "read-only Google Ads Search exporter available locally" in ads["missing_config_details"]
    assert "still planned for this profile" in ads["safe_next_action"]
    assert "not enabled for this profile" in ads["blocked_reason"]
    assert ads["validation_ready"] == "Not available yet"
    assert ads["dashboard_copy_ready"] == "Not available yet"
    assert ads["suggested_command"] == ""
    assert "inn-at-spanish-head" in serialized
    assert "exports/local-real/dashboard-lab/aluma-seo-geo" not in serialized


def test_validate_profile_output_reports_missing_folder(tmp_path):
    profile = _test_profile(tmp_path, source_exists=False)

    report = validate_profile_output(profile)

    assert report.folder_exists is False
    assert report.missing_files == EXPECTED_DASHBOARD_FILES
    assert "output folder is missing" in report.warnings


def test_validate_profile_output_reports_valid_json_metadata(tmp_path):
    profile = _test_profile(tmp_path)
    for filename in EXPECTED_DASHBOARD_FILES:
        _write_json(profile.importer_output_folder / filename, filename)

    report = validate_profile_output(profile)

    assert report.ok is True
    assert report.missing_files == []
    assert report.malformed_json_files == []
    assert all(item.json_valid is True for item in report.files)
    assert all(item.schema_version == "dashboard_lab_provider_summary.v1" for item in report.files)


def test_validate_profile_output_detects_malformed_json(tmp_path):
    profile = _test_profile(tmp_path)
    _write_json(profile.importer_output_folder / "client-profile.json", "client-profile.json")
    (profile.importer_output_folder / "ga4-summary.json").write_text("{bad json", encoding="utf-8")

    report = validate_profile_output(profile)

    assert "ga4-summary.json" in report.malformed_json_files
    assert next(item for item in report.files if item.file == "ga4-summary.json").warning == "malformed JSON"


def test_copy_dry_run_preview_reports_copy_overwrite_and_missing(tmp_path):
    profile = _test_profile(tmp_path)
    _write_json(profile.importer_output_folder / "client-profile.json", "client-profile.json")
    _write_json(profile.importer_output_folder / "ga4-summary.json", "ga4-summary.json")
    profile.dashboard_lab_local_fixture_folder.mkdir(parents=True)
    _write_json(profile.dashboard_lab_local_fixture_folder / "ga4-summary.json", "ga4-summary.json")

    plan = copy_dry_run(profile)

    assert next(item for item in plan if item.file == "client-profile.json").action == "copy"
    assert next(item for item in plan if item.file == "ga4-summary.json").action == "overwrite"
    assert next(item for item in plan if item.file == "gsc-summary.json").action == "skip missing"


def test_copy_rejects_committed_fixture_destination(tmp_path):
    profile = _test_profile(tmp_path)
    unsafe = profile.__class__(
        **{
            **profile.__dict__,
            "dashboard_lab_local_fixture_folder": tmp_path / "musimack-dashboard-lab" / "public" / "fixtures" / "demo-profile",
        }
    )

    with pytest.raises(OperatorConsoleError, match="public/fixtures"):
        copy_dry_run(unsafe)


def test_guarded_copy_only_copies_expected_files_and_reports_missing(tmp_path):
    profile = _test_profile(tmp_path)
    _write_json(profile.importer_output_folder / "client-profile.json", "client-profile.json")
    _write_json(profile.importer_output_folder / "ga4-summary.json", "ga4-summary.json")
    (profile.importer_output_folder / "raw-response.json").write_text("{}", encoding="utf-8")

    results = copy_local_real_to_dashboard_lab(profile)

    assert (profile.dashboard_lab_local_fixture_folder / "client-profile.json").exists()
    assert (profile.dashboard_lab_local_fixture_folder / "ga4-summary.json").exists()
    assert not (profile.dashboard_lab_local_fixture_folder / "raw-response.json").exists()
    assert next(item for item in results if item.file == "client-profile.json").status == "copied"
    assert next(item for item in results if item.file == "gsc-summary.json").status == "skipped missing source"


def _registry(tmp_path: Path) -> Path:
    registry = tmp_path / "profiles.json"
    registry.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "slug": "demo-profile",
                        "display_name": "Demo Profile",
                        "domain": "example.com",
                        "vertical": "demo",
                        "service_model": "demo",
                        "dashboard_lab_route": "/lab/demo-profile",
                        "importer_output_folder": "exports/local-real/dashboard-lab/demo-profile",
                        "dashboard_lab_local_fixture_folder": "../musimack-dashboard-lab/public/local-fixtures/demo-profile",
                        "dashboard_lab_synthetic_fixture_folder": "../musimack-dashboard-lab/public/fixtures/demo-profile",
                        "data_sources": ["ga4", "gsc", "local_falcon"],
                        "capabilities": [
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


def _test_profile(tmp_path, *, source_exists=True) -> DashboardLabProfile:
    source = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile"
    if source_exists:
        source.mkdir(parents=True)
    return DashboardLabProfile(
        slug="demo-profile",
        display_name="Demo Profile",
        domain="example.com",
        vertical="demo",
        service_model="demo",
        dashboard_lab_route="/lab/demo-profile",
        importer_output_folder=source,
        dashboard_lab_local_fixture_folder=tmp_path / "musimack-dashboard-lab" / "public" / "local-fixtures" / "demo-profile",
        dashboard_lab_synthetic_fixture_folder=tmp_path / "musimack-dashboard-lab" / "public" / "fixtures" / "demo-profile",
        data_sources=["ga4", "gsc", "local_falcon"],
    )


def _write_json(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": "dashboard_lab_provider_summary.v1", "label": label}),
        encoding="utf-8",
    )


def _capability(profile: DashboardLabProfile, key: str):
    return next(item for item in profile.capabilities if item.key == key)


def _matrix_row(rows: list[dict], provider_key: str) -> dict:
    return next(item for item in rows if item["provider_key"] == provider_key)


def _phase(sequence: dict, phase_id: str) -> dict:
    return next(item for item in sequence["phases"] if item["id"] == phase_id)
