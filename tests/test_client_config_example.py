import json
from pathlib import Path


EXPECTED_KEYS = {
    "aluma",
    "lucy_escobar",
    "priority_tree_service",
    "pinnacle_contractors",
    "musimack_marketing",
    "steadfast_decks",
    "portland_painting_lead_removal",
    "universal_crystal_cleaning",
    "tualatin_chamber",
    "west_coast_land_renewal",
    "inn_at_spanish_head",
    "the_word_salon",
    "portland_tattoo_company",
}


FORBIDDEN_TERMS = [
    "oauth",
    "token",
    "secret",
    "credential",
    "authorization",
    "private_key",
    "raw_provider",
    "raw_payload",
]


def load_config():
    return json.loads(
        Path("examples/ga4_clients.local.example.json").read_text(encoding="utf-8")
    )


def test_client_config_contains_real_portal_roster():
    config = load_config()

    assert set(config) == EXPECTED_KEYS
    assert len(config) == 13
    assert config["musimack_marketing"]["client_label"] == "Musimack Marketing"
    assert config["musimack_marketing"]["ga4_property_id"] == "310280796"
    assert config["aluma"]["portal_report_id"] == "9fecb93f-b5a3-4998-94d7-c32bb57a2d94"


def test_client_config_has_safe_ytd_operational_fields():
    config = load_config()

    for client in config.values():
        assert client["client_label"]
        assert client["portal_project_id"]
        assert client["ga4_property_id"].isdigit()
        assert client["suggested_export_slug"]
        assert client["suggested_ytd_start_date"] == "2026-01-01"
        assert client["suggested_ytd_end_date"] == "2026-05-19"
        assert client["unrelated_client_email"] == "unrelated.client@musimack.local"
        assert client["assigned_client_email"].endswith("@musimack.local")


def test_client_config_does_not_include_secret_material():
    text = Path("examples/ga4_clients.local.example.json").read_text(encoding="utf-8").lower()

    for term in FORBIDDEN_TERMS:
        assert term not in text
