from pathlib import Path

from scripts.check_client_report_publisher_profile_preflight import (
    format_report,
    run_preflight,
)


def test_preflight_reports_registry_and_missing_env_without_reading_local_config(tmp_path):
    registry = tmp_path / "profiles.json"
    registry.write_text(
        """
        {
          "profiles": [
            {"slug": "aluma-seo-geo"},
            {"slug": "lucy-escobar"},
            {"slug": "pinnacle-contractors"},
            {"slug": "western-wood-structures"},
            {"slug": "avs"}
          ]
        }
        """,
        encoding="utf-8",
    )

    report = run_preflight(env={}, root=tmp_path, local_config_dir=tmp_path, registry_path=registry)

    assert report["local_config_contents_read"] == "no"
    assert report["provider_calls"] == "none"
    assert report["summary"]["profiles_checked"] == 5
    assert report["summary"]["missing_registry_profiles"] == 0
    assert report["summary"]["missing_env_names"] > 0


def test_preflight_checks_path_safety_without_printing_values(tmp_path):
    registry = tmp_path / "profiles.json"
    registry.write_text(
        """
        {
          "profiles": [
            {"slug": "aluma-seo-geo"},
            {"slug": "lucy-escobar"},
            {"slug": "pinnacle-contractors"},
            {"slug": "western-wood-structures"},
            {"slug": "avs"}
          ]
        }
        """,
        encoding="utf-8",
    )
    outside_dir = tmp_path.parent / "outside-preflight"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "token.json"
    outside_file.write_text("not-read", encoding="utf-8")
    inside_file = tmp_path / "token.json"
    inside_file.write_text("not-read", encoding="utf-8")
    env = {
        "ALUMA_GA4_PROPERTY_ID": "123456789",
        "ALUMA_GA4_OAUTH_TOKEN_FILE": str(outside_file),
        "ALUMA_GA4_OAUTH_CLIENT_SECRETS": str(inside_file),
    }

    report = run_preflight(env=env, root=tmp_path, local_config_dir=tmp_path, registry_path=registry)
    text = format_report(report)

    assert "123456789" not in text
    assert str(outside_file) not in text
    assert str(inside_file) not in text
    assert "ALUMA_GA4_PROPERTY_ID: set" in text
    assert "ALUMA_GA4_OAUTH_TOKEN_FILE: set; file exists; outside repo" in text
    assert "ALUMA_GA4_OAUTH_CLIENT_SECRETS: set; file exists; inside repo" in text
    assert report["summary"]["path_values_inside_repo"] == 1


def test_preflight_marks_avs_as_pending_domain_confirmation(tmp_path):
    registry = tmp_path / "profiles.json"
    registry.write_text(
        """
        {
          "profiles": [
            {"slug": "aluma-seo-geo"},
            {"slug": "lucy-escobar"},
            {"slug": "pinnacle-contractors"},
            {"slug": "western-wood-structures"},
            {"slug": "avs"}
          ]
        }
        """,
        encoding="utf-8",
    )

    report = run_preflight(
        env={"AVS_CANONICAL_DOMAIN_PENDING": "yes"},
        root=tmp_path,
        local_config_dir=tmp_path,
        registry_path=registry,
    )
    avs = next(profile for profile in report["profiles"] if profile["slug"] == "avs")

    assert avs["provider_readiness"] == "pending canonical domain confirmation"
    assert [row["name"] for row in avs["env"]] == [
        "AVS_CANONICAL_DOMAIN_PENDING",
        "AVS_GA4_PROPERTY_ID_PENDING",
        "AVS_GSC_SITE_URL_PENDING",
    ]
