import json
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
                {"slug": "inn-at-spanish-head"},
                {"slug": "lucy-escobar"},
                {"slug": "pinnacle-contractors"},
                {"slug": "steadfast-decks-and-fences"},
                {"slug": "western-wood-structures"},
                {"slug": "avs"}
              ]
        }
        """,
        encoding="utf-8",
    )

    report = run_preflight(env={}, root=tmp_path, local_config_dir=tmp_path, registry_path=registry)

    assert report["local_config_contents_read"] == "requested profile only; values redacted"
    assert report["provider_calls"] == "none"
    assert report["summary"]["profiles_checked"] == 7
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


def test_preflight_accepts_alias_and_redacts_direct_local_config_values(tmp_path):
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
    outside_dir = tmp_path.parent / "outside-preflight-alias"
    outside_dir.mkdir(exist_ok=True)
    client = outside_dir / "client.json"
    token = outside_dir / "token.json"
    client.write_text("not-read", encoding="utf-8")
    token.write_text("not-read", encoding="utf-8")
    (tmp_path / "aluma.local.json").write_text(
        json.dumps(
            {
                "profile": "aluma",
                "ga4": {
                    "property_id": "123456789",
                    "oauth_client_secrets_file": str(client),
                    "oauth_token_file": str(token),
                },
                "gsc": {
                    "site_url": "https://example.test/",
                    "oauth_client_secrets_file": str(client),
                    "oauth_token_file": str(token),
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_preflight(
        profiles=["aluma"],
        env={},
        root=tmp_path,
        local_config_dir=tmp_path,
        registry_path=registry,
    )
    text = format_report(report)

    assert "Profile: aluma -> aluma-seo-geo" in text
    assert "123456789" not in text
    assert str(client) not in text
    assert str(token) not in text
    assert "GA4: property configured; client secrets configured; exists; outside repo; token configured; exists; outside repo" in text
