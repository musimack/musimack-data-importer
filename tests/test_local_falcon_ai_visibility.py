from pathlib import Path

from src.local_falcon_api_fetcher import LocalFalconApiFetcher, LocalFalconApiFetchRequest
from src.local_falcon_api_plan import LocalFalconApiReportPlan
from src.local_falcon_api_responses import (
    load_synthetic_api_fixture,
    normalize_api_brand_observations,
    normalize_api_brand_phrases,
    normalize_api_grid_points,
    normalize_api_report_to_keyword_scan,
)
from src.local_falcon_importer import validate_local_falcon_summary


FIXTURES = Path(__file__).parent / "fixtures" / "local_falcon_api"


class AiVisibilityTransport:
    def __init__(self):
        self.report = load_synthetic_api_fixture(FIXTURES / "ai_visibility_report_response.json")

    def get_report_summary(self, report_id):
        return self.report

    def get_grid_points(self, report_id):
        return self.report

    def get_competitors(self, report_id):
        return {
            "success": True,
            "data": {
                "businesses": [
                    {
                        "name": "Demo Visibility Clinic",
                        "rank": 1,
                        "found_points": 9
                    }
                ]
            }
        }

    def get_ai_analysis(self, report_id):
        return self.report


def test_ai_visibility_response_normalizes_brand_observations_and_phrases():
    payload = load_synthetic_api_fixture(FIXTURES / "ai_visibility_report_response.json")
    scan = normalize_api_report_to_keyword_scan(payload, ai_response=payload)

    assert scan["brand_observations"][0] == {
        "brand_name": "Demo Visibility Clinic",
        "relationship": "client",
        "observation_count": 4,
        "map_points_observed": 4,
        "observation_sequence": 1,
        "sentiment": "positive",
        "share_of_ai_voice": 12.5,
    }
    assert "rank" not in scan["brand_observations"][0]
    assert scan["brand_phrases"][0] == {
        "phrase": "trusted demo provider",
        "count": 4,
        "sentiment": "positive",
        "brand_name": "Demo Visibility Clinic",
    }
    assert scan["ai_visibility_metrics"]["mentions_client"] is True
    assert scan["ai_visibility_metrics"]["client_brand_name"] == "Demo Visibility Clinic"
    assert scan["ai_visibility_metrics"]["client_observation_count"] == 4
    assert scan["ai_visibility_metrics"]["client_sentiment"] == "positive"
    assert scan["ai_visibility_metrics"]["share_of_ai_voice"] == 12.5
    assert scan["ai_visibility_metrics"]["positive_phrase_count"] == 4
    assert scan["ai_visibility_metrics"]["neutral_phrase_count"] == 2


def test_ai_visibility_response_preserves_point_level_observations():
    payload = load_synthetic_api_fixture(FIXTURES / "ai_visibility_report_response.json")
    points = normalize_api_grid_points(payload, "Demo Visibility Clinic")

    assert points[0]["col"] == 0
    assert points[0]["observed"] is True
    assert points[0]["observation_sequence"] == 1
    assert points[0]["ai_visibility_value"] == 1
    assert points[0]["brand_name"] == "Demo Visibility Clinic"
    assert points[0]["place_id"] == "place-other"
    assert points[0]["relationship"] == "client"
    assert points[0]["sentiment"] == "positive"
    assert points[0]["result_count"] == 2
    assert points[0].get("rank") is None
    assert points[2]["observed"] is False
    assert points[3]["observation_sequence"] == 3
    assert points[3]["ai_visibility_value"] == 1
    assert points[3]["brand_name"] == "Example Wellness Studio"
    assert points[3]["place_id"] == "place-other"
    assert points[4]["observed"] is False
    assert points[5]["observation_sequence"] == 1
    assert points[5]["brand_name"] == "Demo Visibility Clinic"
    assert all(point.get("rank") is None for point in points)


def test_ai_visibility_scan_does_not_treat_brand_observations_as_competitors(tmp_path):
    result = LocalFalconApiFetcher(AiVisibilityTransport()).fetch(
        LocalFalconApiFetchRequest(
            profile="all-services-client",
            output=tmp_path / "local-falcon-summary.json",
            reports=[
                LocalFalconApiReportPlan(
                    keyword="can you recommend a good demo provider?",
                    query="can you recommend a good demo provider?",
                    report_id="fake-ai-report",
                    source_id="chatgpt",
                    source_label="ChatGPT",
                    query_type="ai_visibility_prompt",
                    scan_kind="ai_visibility_map",
                )
            ],
        )
    )
    scan = result.summary["keyword_scans"][0]

    assert scan["query_type"] == "ai_visibility_prompt"
    assert scan["prompt"] == "can you recommend a good demo provider?"
    assert scan["competitors"] == []
    assert scan["brand_observations"][0]["brand_name"] == "Demo Visibility Clinic"
    assert scan["ai_visibility_points"][0] == {
        "grid_index": 1,
        "row": 0,
        "col": 0,
        "latitude": 35.11,
        "longitude": -101.21,
        "observed": True,
        "ai_visibility_status": "observed",
        "observation_sequence": 2,
        "ai_visibility_value": 2,
        "brand_name": "Demo Visibility Clinic",
        "place_id": "place-client",
        "relationship": "client",
        "share_of_ai_voice": 12.5,
        "sentiment": "positive",
        "result_count": 2,
    }
    assert scan["ai_visibility_points"][2]["observed"] is False
    assert scan["ai_visibility_points"][3]["relationship"] == "mentioned_brand"
    assert scan["ai_visibility_points"][3]["share_of_ai_voice"] == 6.25
    assert scan["ai_visibility_points"][5]["observation_sequence"] == 1
    assert "rank" not in scan["ai_visibility_points"][0]
    assert scan["ai_visibility_metrics"]["map_point_count"] == 9
    assert scan["ai_visibility_metrics"]["observed_point_count"] == 4
    assert scan["ai_visibility_metrics"]["not_observed_point_count"] == 5
    assert scan["ai_visibility_metrics"]["unique_brand_count"] == 2
    assert scan["ai_visibility_metrics"]["total_brand_mentions"] == 5
    assert scan["ai_visibility_metrics"]["mentions_client"] is True
    assert scan["ai_visibility_metrics"]["client_brand_name"] == "Demo Visibility Clinic"
    assert scan["ai_visibility_metrics"]["client_observation_count"] == 4
    assert scan["ai_visibility_metrics"]["client_best_observation_sequence"] == 1
    assert scan["ai_visibility_metrics"]["client_average_observation_sequence"] == 1.67
    assert scan["ai_visibility_metrics"]["share_of_ai_voice"] == 12.5
    assert scan["brand_observations"][0]["relationship"] == "client"
    assert scan["brand_observations"][0]["place_id"] == "place-client"
    assert scan["brand_observations"][0]["map_points_observed"] == 3
    assert scan["brand_observations"][0]["best_observation_sequence"] == 1
    assert scan["brand_observations"][0]["average_observation_sequence"] == 1.67
    assert scan["brand_observations"][0]["share_of_ai_voice"] == 12.5
    assert scan["brand_observations"][1]["relationship"] == "mentioned_brand"
    assert scan["action_bridge"]
    assert not any("competitor" in item.get("area", "").lower() for item in scan["action_bridge"])


def test_validator_accepts_ai_visibility_fields_with_warnings_only_for_missing_optional_competitors(tmp_path):
    result = LocalFalconApiFetcher(AiVisibilityTransport()).fetch(
        LocalFalconApiFetchRequest(
            profile="all-services-client",
            output=tmp_path / "local-falcon-summary.json",
            reports=[
                LocalFalconApiReportPlan(
                    keyword="can you recommend a good demo provider?",
                    query="can you recommend a good demo provider?",
                    report_id="fake-ai-report",
                    source_id="chatgpt",
                    source_label="ChatGPT",
                    query_type="ai_visibility_prompt",
                    scan_kind="ai_visibility_map",
                )
            ],
        )
    )

    validation = validate_local_falcon_summary(result.summary)

    assert not any("brand observations" in warning for warning in validation.warnings)
    assert not any("brand phrases" in warning for warning in validation.warnings)
    assert not any("AI visibility metrics" in warning for warning in validation.warnings)
    assert not any("AI visibility point" in warning for warning in validation.warnings)
    assert validation.keyword_summaries[0]["ai_visibility_point_count"] == 9


def test_ai_visibility_nested_results_do_not_invent_brand_phrases(tmp_path):
    payload = {
        "success": True,
        "data": {
            "keyword": "synthetic AI prompt",
            "ai_place_id": "place-client",
            "places": {"place-client": {"name": "Synthetic Client", "saiv": 9.5}},
            "data_points": [
                {
                    "row": 0,
                    "col": 0,
                    "lat": 35.0,
                    "lng": -101.0,
                    "rank": True,
                    "found": True,
                    "results": [{"name": "Synthetic Client", "place_id": "place-client", "rank": 1}],
                }
            ],
            "ai_analysis": {"summary": "Synthetic summary."},
        },
    }

    class NestedOnlyTransport:
        def get_report_summary(self, report_id):
            return payload

        def get_grid_points(self, report_id):
            return payload

        def get_competitors(self, report_id):
            return None

        def get_ai_analysis(self, report_id):
            return payload

    result = LocalFalconApiFetcher(NestedOnlyTransport()).fetch(
        LocalFalconApiFetchRequest(
            profile="all-services-client",
            output=tmp_path / "local-falcon-summary.json",
            reports=[
                LocalFalconApiReportPlan(
                    keyword="synthetic AI prompt",
                    query="synthetic AI prompt",
                    report_id="fake-ai-report",
                    source_id="chatgpt",
                    source_label="ChatGPT",
                    query_type="ai_visibility_prompt",
                    scan_kind="ai_visibility_map",
                )
            ],
        )
    )
    scan = result.summary["keyword_scans"][0]

    assert scan["brand_phrases"] == []
    assert scan["ai_visibility_points"][0]["observation_sequence"] == 1
    assert scan["ai_visibility_points"][0]["ai_visibility_value"] == 1
    assert scan["ai_visibility_points"][0]["relationship"] == "client"
    assert scan["brand_observations"][0]["share_of_ai_voice"] == 9.5


def test_google_maps_fixture_still_uses_competitor_model():
    report = load_synthetic_api_fixture(FIXTURES / "report_summary_response.json")
    grid = load_synthetic_api_fixture(FIXTURES / "report_grid_points_response.json")
    competitors = load_synthetic_api_fixture(FIXTURES / "competitor_report_response.json")

    scan = normalize_api_report_to_keyword_scan(report, grid_response=grid, competitor_response=competitors)

    assert scan["competitors"]
    assert "brand_observations" not in scan
    assert "brand_phrases" not in scan
    assert "ai_visibility_metrics" not in scan
    assert "ai_visibility_points" not in scan


def test_brand_helpers_tolerate_missing_ai_fields():
    report = load_synthetic_api_fixture(FIXTURES / "report_summary_response.json")

    assert normalize_api_brand_observations(report) == []
    assert normalize_api_brand_phrases(report) == []
