from src.local_falcon_ai_diagnostic import diagnose_ai_report_shape, diagnostic_to_dict
from src.local_falcon_api_plan import LocalFalconApiReportPlan


def test_ai_diagnostic_finds_nested_point_observation_shapes_without_values():
    diagnostic = diagnose_ai_report_shape(
        {
            "data": {
                "data_points": [
                    {
                        "row": 0,
                        "col": 0,
                        "observed": True,
                        "results": [
                            {
                                "position": 1,
                                "value": 1,
                                "provider": "Synthetic Provider",
                                "sentiment": "positive",
                            }
                        ],
                    },
                    {
                        "row": 0,
                        "col": 1,
                        "mentioned": True,
                        "sequence": 2,
                        "brand_name": "Synthetic Brand",
                    },
                    {
                        "row": 0,
                        "col": 2,
                        "observed": False,
                    },
                ],
                "ai_visibility": {
                    "brand_phrases": [{"phrase": "synthetic phrase"}],
                    "ai_visibility_metrics": {"share_of_ai_voice": 22.5},
                },
            }
        },
        _ai_report(),
    )
    payload = diagnostic_to_dict(diagnostic)

    assert payload["source_label"] == "ChatGPT"
    assert payload["total_point_like_objects"] == 3
    assert payload["nested_result_bearing_point_count"] == 1
    assert payload["points_with_numeric_values"] == 1
    assert payload["points_with_string_labels"] == 2
    assert payload["points_with_observation_sequence_fields"] == 1
    assert payload["points_with_rank_or_position_fields"] == 1
    assert payload["points_with_observed_mentioned_found_fields"] == 3
    assert "data.data_points[0].results[0].value" in payload["candidate_marker_value_paths"]
    assert "data.data_points[0].results[0].position" in payload["candidate_marker_value_paths"]
    assert "data.data_points[1].sequence" in payload["candidate_marker_value_paths"]
    assert "data.data_points[0].results[0].provider" in payload["candidate_brand_provider_paths"]
    assert "data.data_points[1].brand_name" in payload["candidate_brand_provider_paths"]
    assert "data.data_points[0].results[0].sentiment" in payload["candidate_sentiment_paths"]
    assert "data.ai_visibility.brand_phrases[0].phrase" in payload["candidate_phrase_paths"]
    assert "data.ai_visibility.ai_visibility_metrics.share_of_ai_voice" in payload["candidate_saiv_paths"]
    assert all("Synthetic" not in str(sample) for sample in payload["safe_sample_shapes"])


def test_ai_diagnostic_finds_direct_value_and_found_fields():
    diagnostic = diagnose_ai_report_shape(
        {
            "data_points": [
                {"row": 0, "col": 0, "found": True, "value": 5, "entity": "Synthetic Entity"},
                {"row": 0, "col": 1},
            ]
        },
        _ai_report(source_label="Google Gemini"),
    )

    assert diagnostic.total_point_like_objects == 2
    assert diagnostic.points_with_numeric_values == 1
    assert diagnostic.points_with_observed_mentioned_found_fields == 1
    assert "data_points[0].value" in diagnostic.candidate_marker_value_paths
    assert "data_points[0].entity" in diagnostic.candidate_brand_provider_paths


def test_ai_diagnostic_handles_points_with_no_observations():
    diagnostic = diagnose_ai_report_shape(
        {"grid_points": [{"row": 0, "col": 0}, {"row": 0, "col": 1}]},
        _ai_report(source_label="Google AI Overviews"),
    )

    assert diagnostic.total_point_like_objects == 2
    assert diagnostic.nested_result_bearing_point_count == 0
    assert diagnostic.points_with_numeric_values == 0
    assert diagnostic.points_with_observed_mentioned_found_fields == 0
    assert diagnostic.candidate_marker_value_paths == []


def test_google_maps_rank_response_is_not_ai_marker_value_candidate():
    diagnostic = diagnose_ai_report_shape(
        {
            "data": {
                "data_points": [
                    {"row": 0, "col": 0, "rank": 1, "business_name": "Synthetic Business"},
                    {"row": 0, "col": 1, "position": 2, "business_name": "Synthetic Business"},
                ]
            }
        },
        LocalFalconApiReportPlan(
            keyword="synthetic map keyword",
            query="synthetic map keyword",
            report_id="fake-google-report-id",
            source_label="Google Maps",
            query_type="map_keyword",
            scan_kind="map_visibility",
        ),
    )

    assert diagnostic.total_point_like_objects == 2
    assert diagnostic.points_with_rank_or_position_fields == 2
    assert diagnostic.candidate_marker_value_paths == []


def _ai_report(source_label="ChatGPT") -> LocalFalconApiReportPlan:
    return LocalFalconApiReportPlan(
        keyword="synthetic prompt",
        query="synthetic prompt",
        report_id="fake-ai-report-id",
        source_label=source_label,
        query_type="ai_visibility_prompt",
        scan_kind="ai_visibility_map",
    )
