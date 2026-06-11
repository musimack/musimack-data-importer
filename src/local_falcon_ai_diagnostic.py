from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .local_falcon_api_plan import LocalFalconApiReportPlan


POINT_CONTAINER_KEYS = {"data_points", "grid_points", "points", "map_points", "local_prompt_results"}
RESULT_KEYS = {"results", "result"}
NUMERIC_SIGNAL_KEYS = {
    "ai_visibility_value",
    "visibility_value",
    "observation_value",
    "value",
    "score",
}
SEQUENCE_SIGNAL_KEYS = {"observation_sequence", "sequence", "observed_order", "order"}
RANK_SIGNAL_KEYS = {"rank", "position"}
OBSERVED_SIGNAL_KEYS = {"observed", "mentioned", "found"}
BRAND_SIGNAL_KEYS = {"brand", "brands", "brand_name", "business", "business_name", "provider", "entity", "place", "name"}
SENTIMENT_SIGNAL_KEYS = {"sentiment", "brand_sentiment", "phrase_sentiment"}
PHRASE_SIGNAL_KEYS = {"phrase", "phrases", "brand_phrases", "phrase_mentions", "ai_phrases"}
SAIV_SIGNAL_KEYS = {"saiv", "share", "share_of_ai_voice", "voice_share"}
LABEL_SIGNAL_KEYS = BRAND_SIGNAL_KEYS | PHRASE_SIGNAL_KEYS | {"label", "title", "text", "content"}


@dataclass(frozen=True)
class LocalFalconAiReportDiagnostic:
    source_label: str
    query_type: str
    scan_kind: str
    report_id_redacted: str
    total_point_like_objects: int
    nested_result_bearing_point_count: int
    points_with_numeric_values: int
    points_with_string_labels: int
    points_with_observation_sequence_fields: int
    points_with_rank_or_position_fields: int
    points_with_observed_mentioned_found_fields: int
    candidate_marker_value_paths: list[str]
    candidate_brand_provider_paths: list[str]
    candidate_sentiment_paths: list[str]
    candidate_phrase_paths: list[str]
    candidate_saiv_paths: list[str]
    safe_sample_shapes: list[dict[str, Any]]


def diagnose_ai_report_shape(
    payload: dict[str, Any],
    report: LocalFalconApiReportPlan,
    *,
    max_samples: int = 20,
) -> LocalFalconAiReportDiagnostic:
    point_objects = _find_point_objects(payload)
    all_leaf_nodes = list(_walk_leaf_nodes(payload))
    point_leaf_nodes = [leaf for path, point in point_objects for leaf in _walk_leaf_nodes(point, path)]
    marker_keys = NUMERIC_SIGNAL_KEYS | SEQUENCE_SIGNAL_KEYS | OBSERVED_SIGNAL_KEYS
    if report.query_type == "ai_visibility_prompt":
        marker_keys = marker_keys | RANK_SIGNAL_KEYS

    return LocalFalconAiReportDiagnostic(
        source_label=report.source_label or "Local Falcon AI",
        query_type=report.query_type or "unknown",
        scan_kind=report.scan_kind or "unknown",
        report_id_redacted=_redacted_report_id(report.report_id),
        total_point_like_objects=len(point_objects),
        nested_result_bearing_point_count=sum(1 for _, point in point_objects if _has_nested_results(point)),
        points_with_numeric_values=sum(1 for _, point in point_objects if _point_has_key_kind(point, NUMERIC_SIGNAL_KEYS, "numeric")),
        points_with_string_labels=sum(1 for _, point in point_objects if _point_has_key_kind(point, LABEL_SIGNAL_KEYS, "string")),
        points_with_observation_sequence_fields=sum(1 for _, point in point_objects if _point_has_key(point, SEQUENCE_SIGNAL_KEYS)),
        points_with_rank_or_position_fields=sum(1 for _, point in point_objects if _point_has_key(point, RANK_SIGNAL_KEYS)),
        points_with_observed_mentioned_found_fields=sum(1 for _, point in point_objects if _point_has_key(point, OBSERVED_SIGNAL_KEYS)),
        candidate_marker_value_paths=_unique_sorted(
            [
                leaf.path
                for leaf in point_leaf_nodes
                if _key_matches(leaf.key, marker_keys)
            ]
        ),
        candidate_brand_provider_paths=_unique_sorted(
            [leaf.path for leaf in all_leaf_nodes if _key_matches(leaf.key, BRAND_SIGNAL_KEYS)]
        ),
        candidate_sentiment_paths=_unique_sorted(
            [leaf.path for leaf in all_leaf_nodes if _key_matches(leaf.key, SENTIMENT_SIGNAL_KEYS)]
        ),
        candidate_phrase_paths=_unique_sorted(
            [leaf.path for leaf in all_leaf_nodes if _key_matches(leaf.key, PHRASE_SIGNAL_KEYS)]
        ),
        candidate_saiv_paths=_unique_sorted(
            [leaf.path for leaf in all_leaf_nodes if _key_matches(leaf.key, SAIV_SIGNAL_KEYS)]
        ),
        safe_sample_shapes=[
            _safe_sample(leaf)
            for leaf in _prioritized_samples(point_leaf_nodes, all_leaf_nodes, max_samples=max_samples)
        ],
    )


def diagnostic_to_dict(diagnostic: LocalFalconAiReportDiagnostic) -> dict[str, Any]:
    return {
        "source_label": diagnostic.source_label,
        "query_type": diagnostic.query_type,
        "scan_kind": diagnostic.scan_kind,
        "report_id_redacted": diagnostic.report_id_redacted,
        "total_point_like_objects": diagnostic.total_point_like_objects,
        "nested_result_bearing_point_count": diagnostic.nested_result_bearing_point_count,
        "points_with_numeric_values": diagnostic.points_with_numeric_values,
        "points_with_string_labels": diagnostic.points_with_string_labels,
        "points_with_observation_sequence_fields": diagnostic.points_with_observation_sequence_fields,
        "points_with_rank_or_position_fields": diagnostic.points_with_rank_or_position_fields,
        "points_with_observed_mentioned_found_fields": diagnostic.points_with_observed_mentioned_found_fields,
        "candidate_marker_value_paths": diagnostic.candidate_marker_value_paths,
        "candidate_brand_provider_paths": diagnostic.candidate_brand_provider_paths,
        "candidate_sentiment_paths": diagnostic.candidate_sentiment_paths,
        "candidate_phrase_paths": diagnostic.candidate_phrase_paths,
        "candidate_saiv_paths": diagnostic.candidate_saiv_paths,
        "safe_sample_shapes": diagnostic.safe_sample_shapes,
    }


@dataclass(frozen=True)
class _LeafNode:
    path: str
    key: str
    value: Any


def _find_point_objects(payload: Any) -> list[tuple[str, dict[str, Any]]]:
    points: list[tuple[str, dict[str, Any]]] = []

    def walk(value: Any, path: str, parent_key: str | None = None) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                nested_path = f"{path}.{key}" if path else key
                walk(nested, nested_path, key)
            return
        if isinstance(value, list):
            if parent_key and parent_key in POINT_CONTAINER_KEYS:
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        points.append((f"{path}[{index}]", item))
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", parent_key)

    walk(payload, "")
    return points


def _walk_leaf_nodes(payload: Any, path: str = "") -> list[_LeafNode]:
    leaves: list[_LeafNode] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            nested_path = f"{path}.{key}" if path else key
            if isinstance(value, dict | list):
                leaves.extend(_walk_leaf_nodes(value, nested_path))
            else:
                leaves.append(_LeafNode(path=nested_path, key=key, value=value))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            nested_path = f"{path}[{index}]"
            if isinstance(value, dict | list):
                leaves.extend(_walk_leaf_nodes(value, nested_path))
            else:
                leaves.append(_LeafNode(path=nested_path, key=_path_key(path), value=value))
    return leaves


def _has_nested_results(point: dict[str, Any]) -> bool:
    for key in RESULT_KEYS:
        value = point.get(key)
        if isinstance(value, list) and any(isinstance(item, dict) for item in value):
            return True
        if isinstance(value, dict):
            return True
    return False


def _point_has_key(point: dict[str, Any], keys: set[str]) -> bool:
    return any(_key_matches(leaf.key, keys) for leaf in _walk_leaf_nodes(point))


def _point_has_key_kind(point: dict[str, Any], keys: set[str], kind: str) -> bool:
    return any(_key_matches(leaf.key, keys) and _value_kind(leaf.value) == kind for leaf in _walk_leaf_nodes(point))


def _key_matches(key: str, candidates: set[str]) -> bool:
    normalized = key.strip().lower()
    return normalized in candidates or any(part in normalized for part in candidates if len(part) >= 5)


def _prioritized_samples(
    point_leaf_nodes: list[_LeafNode],
    all_leaf_nodes: list[_LeafNode],
    *,
    max_samples: int,
) -> list[_LeafNode]:
    candidates = [
        leaf
        for leaf in point_leaf_nodes
        if _key_matches(
            leaf.key,
            NUMERIC_SIGNAL_KEYS
            | SEQUENCE_SIGNAL_KEYS
            | RANK_SIGNAL_KEYS
            | OBSERVED_SIGNAL_KEYS
            | BRAND_SIGNAL_KEYS
            | SENTIMENT_SIGNAL_KEYS,
        )
    ]
    candidates.extend(
        leaf
        for leaf in all_leaf_nodes
        if _key_matches(leaf.key, PHRASE_SIGNAL_KEYS | SAIV_SIGNAL_KEYS)
    )
    seen = set()
    samples = []
    for leaf in candidates:
        if leaf.path in seen:
            continue
        seen.add(leaf.path)
        samples.append(leaf)
        if len(samples) >= max_samples:
            break
    return samples


def _safe_sample(leaf: _LeafNode) -> dict[str, Any]:
    kind = _value_kind(leaf.value)
    return {
        "path": leaf.path,
        "type": type(leaf.value).__name__,
        "example_kind": kind,
        "example_redacted": kind in {"string", "numeric", "boolean"},
    }


def _value_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float) and not isinstance(value, bool):
        return "numeric"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    return "other"


def _path_key(path: str) -> str:
    return path.rsplit(".", maxsplit=1)[-1].split("[", maxsplit=1)[0]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _redacted_report_id(value: str) -> str:
    text = str(value)
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"
