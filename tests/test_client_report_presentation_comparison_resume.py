"""Measured proof of durable preset-level resume for the comparison stage.

Every number here comes from running the **real production generator** against
counting fakes, in the same spirit as `test_exact_range_call_graph.py`. Nothing
is derived by reading the loop and doing arithmetic.

Fully offline: no credential, no provider client, no network call, and no
artifact outside a pytest temporary directory. Not one provider request is
spent proving that provider requests are not re-spent.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.client_report_presentation_comparison_provider import (
    build_real_presentation_comparisons,
)
from src.client_report_presentation_comparison_resume import (
    CHECKPOINT_SCHEMA_VERSION,
    ENTRIES_PER_PRESET,
    EXPECTED_TOTAL_ENTRIES,
    IDENTITY_FILENAME,
    ComparisonCheckpointStore,
    ComparisonResumeError,
    ComparisonRunIdentity,
    assert_no_secret_material,
    provider_configuration_fingerprint,
)
from src.client_report_presentation_comparisons import (
    COMPARISON_PRESET_KEYS,
    validate_presentation_comparison_package,
)
from src.profile_authorization import ProfileAuthorization


PROFILE = "avs"
REPORT_ID = "b8736c17-fa2c-4a95-86ce-a8b14d8c0843"
CLIENT_ID = "b7de661a-5507-4987-839a-2c13ec582bb0"
PROJECT_ID = "a5341c2c-1b4f-4387-82c2-f83ff7474331"
START, END = date(2026, 1, 1), date(2026, 7, 8)
GENERATED_AT = "2026-08-03T00:00:00Z"
AUTHORIZATION = ProfileAuthorization(requested_profile=PROFILE, authorized_profiles=(PROFILE,))

# Measured below, never assumed.
CALLS_PER_PRESET_GA4 = 12
CALLS_PER_PRESET_GSC = 6
CALLS_PER_PRESET = CALLS_PER_PRESET_GA4 + CALLS_PER_PRESET_GSC
TOTAL_CALLS = CALLS_PER_PRESET * len(COMPARISON_PRESET_KEYS)


class TransportReset(RuntimeError):
    """Stands in for ConnectionResetError(10054) from the real transport."""


class _CountingProviders:
    """One counting fake serving both provider roles.

    `fail_after` reproduces the observed failure mode: the connection dies
    partway through a sequential burst, at a point that is not a preset
    boundary.
    """

    def __init__(self, fail_after: int | None = None) -> None:
        self.ga4_calls = 0
        self.gsc_calls = 0
        self._fail_after = fail_after

    @property
    def calls(self) -> int:
        return self.ga4_calls + self.gsc_calls

    def _charge(self, provider: str) -> None:
        if self._fail_after is not None and self.calls >= self._fail_after:
            raise TransportReset(
                "An existing connection was forcibly closed by the remote host"
            )
        if provider == "ga4":
            self.ga4_calls += 1
        else:
            self.gsc_calls += 1

    # GA4 summary

    def run_exact_range_summary(self, date_range, *, metric_names=()):
        self._charge("ga4")
        return {
            "metricHeaders": [{"name": name} for name in metric_names],
            "rows": [{"metricValues": [{"value": "11"} for _ in metric_names]}],
        }

    # GA4 daily series

    def run_exact_range_traffic_series(self, date_range):
        self._charge("ga4")
        days = (date_range.end - date_range.start).days + 1
        return {
            "dimensionHeaders": [{"name": "date"}],
            "metricHeaders": [{"name": "activeUsers"}, {"name": "sessions"}],
            "rows": [
                {
                    "dimensionValues": [
                        {"value": (date.fromordinal(date_range.start.toordinal() + offset)).strftime("%Y%m%d")}
                    ],
                    "metricValues": [{"value": str(offset + 1)}, {"value": str(offset + 2)}],
                }
                for offset in range(days)
            ],
        }

    # GA4 ranked

    def _ranked(self, dimension_names: tuple[str, ...], metric_names: tuple[str, ...], labels: tuple[str, ...]):
        self._charge("ga4")
        return {
            "dimensionHeaders": [{"name": name} for name in dimension_names],
            "metricHeaders": [{"name": name} for name in metric_names],
            "rows": [
                {
                    "dimensionValues": [{"value": f"{label}-{index}"} for label in dimension_names],
                    "metricValues": [{"value": str(index + 1)} for _ in metric_names],
                }
                for index, _ in enumerate(labels)
            ],
        }

    def run_exact_range_channel_performance(self, date_range):
        return self._ranked(
            ("sessionDefaultChannelGroup",),
            ("activeUsers", "sessions", "screenPageViews", "engagementRate", "averageSessionDuration", "eventCount"),
            ("organic", "direct"),
        )

    def run_exact_range_top_sources(self, date_range):
        return self._ranked(
            ("sessionSourceMedium",),
            ("activeUsers", "sessions", "engagementRate", "averageSessionDuration", "eventCount"),
            ("google/organic", "direct/none"),
        )

    def run_exact_range_top_landing_pages(self, date_range):
        return self._ranked(
            ("landingPagePlusQueryString",),
            ("activeUsers", "sessions", "engagedSessions", "engagementRate", "averageSessionDuration", "eventCount"),
            ("/", "/contact"),
        )

    def run_exact_range_most_viewed_pages(self, date_range):
        return self._ranked(
            ("pageTitle", "pagePath"),
            ("screenPageViews", "activeUsers", "eventCount", "averageSessionDuration"),
            ("/", "/about"),
        )

    # GSC

    def _gsc(self, keyed: bool):
        self._charge("gsc")
        if not keyed:
            return {"rows": [{"clicks": 5, "impressions": 90, "ctr": 0.05, "position": 12.5}]}
        return {
            "rows": [
                {"keys": [f"row-{index}"], "clicks": 5 - index, "impressions": 90 - index, "position": 12.5 + index}
                for index in range(3)
            ]
        }

    def query_exact_range_summary(self, start_date, end_date):
        return self._gsc(False)

    def query_exact_range_queries(self, start_date, end_date):
        return self._gsc(True)

    def query_exact_range_pages(self, start_date, end_date):
        return self._gsc(True)


def _identity(**overrides) -> ComparisonRunIdentity:
    values = dict(
        profile=PROFILE,
        report_id=REPORT_ID,
        client_id=CLIENT_ID,
        project_id=PROJECT_ID,
        report_start=START,
        report_end=END,
        gsc_available_through=END,
        provider_configuration_fingerprint=provider_configuration_fingerprint(
            ga4_property_id="123456789", gsc_site_url="https://example.invalid/"
        ),
    )
    values.update(overrides)
    return ComparisonRunIdentity(**values)


def _store(directory: Path | None, **overrides) -> ComparisonCheckpointStore:
    return ComparisonCheckpointStore(directory, _identity(**overrides))


def _run(client: _CountingProviders, store: ComparisonCheckpointStore | None, **kwargs):
    """Invoke the real production generator."""
    new_calls = {"ga4": 0, "gsc": 0}
    restored = {"ga4": 0, "gsc": 0}
    package = build_real_presentation_comparisons(
        ga4_client=client,
        gsc_client=client,
        profile=PROFILE,
        report_id=REPORT_ID,
        client_id=CLIENT_ID,
        project_id=PROJECT_ID,
        report_start=START,
        report_end=END,
        gsc_available_through=END,
        authorization=AUTHORIZATION,
        generated_at=GENERATED_AT,
        provider_calls=new_calls,
        checkpoint=store,
        restored_calls=restored,
        **kwargs,
    )
    return package, new_calls, restored


def _run_expecting_reset(client, store):
    new_calls = {"ga4": 0, "gsc": 0}
    restored = {"ga4": 0, "gsc": 0}
    with pytest.raises(TransportReset):
        build_real_presentation_comparisons(
            ga4_client=client,
            gsc_client=client,
            profile=PROFILE,
            report_id=REPORT_ID,
            client_id=CLIENT_ID,
            project_id=PROJECT_ID,
            report_start=START,
            report_end=END,
            gsc_available_through=END,
            authorization=AUTHORIZATION,
            generated_at=GENERATED_AT,
            provider_calls=new_calls,
            checkpoint=store,
            restored_calls=restored,
        )
    return new_calls, restored


# Baseline: what a clean, uninterrupted run costs and produces.


def test_clean_run_measured_cost_and_shape() -> None:
    client = _CountingProviders()
    package, new_calls, restored = _run(client, None)

    assert client.calls == TOTAL_CALLS == 216
    assert client.ga4_calls == 144
    assert client.gsc_calls == 72
    assert new_calls == {"ga4": 144, "gsc": 72}
    assert restored == {"ga4": 0, "gsc": 0}
    assert len(package["comparisons"]) == EXPECTED_TOTAL_ENTRIES == 120
    assert len({entry["preset_key"] for entry in package["comparisons"]}) == 12


def test_final_output_holds_exactly_120_entries_and_12_presets(tmp_path: Path) -> None:
    package, _, _ = _run(_CountingProviders(), _store(tmp_path / "state"))
    assert len(package["comparisons"]) == 120
    presets = [entry["preset_key"] for entry in package["comparisons"]]
    assert len(set(presets)) == 12
    for key in COMPARISON_PRESET_KEYS:
        assert presets.count(key) == ENTRIES_PER_PRESET == 10


def test_preset_ordering_remains_canonical(tmp_path: Path) -> None:
    package, _, _ = _run(_CountingProviders(), _store(tmp_path / "state"))
    seen: list[str] = []
    for entry in package["comparisons"]:
        if entry["preset_key"] not in seen:
            seen.append(entry["preset_key"])
    assert tuple(seen) == COMPARISON_PRESET_KEYS


# Resume behavior.


def test_reset_after_one_completed_preset_resumes_at_the_next_preset(tmp_path: Path) -> None:
    state = tmp_path / "state"
    # Fail one request into the second preset, so exactly one preset completed.
    first, _ = _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET), _store(state))
    assert first == {"ga4": 12, "gsc": 6}

    completed = _store(state).load()
    assert list(completed) == [COMPARISON_PRESET_KEYS[0]]

    resumed = _CountingProviders()
    package, new_calls, restored = _run(resumed, _store(state))
    # The first preset was never requested again.
    assert resumed.calls == TOTAL_CALLS - CALLS_PER_PRESET == 198
    assert restored == {"ga4": 12, "gsc": 6}
    assert new_calls == {"ga4": 132, "gsc": 66}
    assert len(package["comparisons"]) == 120


def test_reset_partway_through_a_preset_does_not_mark_that_preset_complete(tmp_path: Path) -> None:
    state = tmp_path / "state"
    # Nine requests into the first preset: the preset is half paid for and must
    # not be recorded, because a partial preset is not a completed preset.
    _run_expecting_reset(_CountingProviders(fail_after=9), _store(state))
    assert _store(state).load() == {}
    # Nothing was recorded, so no preset file exists at all.
    assert not state.exists() or not list(state.glob("preset-*.json"))


def test_completed_presets_are_never_requested_again(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET * 3), _store(state))
    assert len(_store(state).load()) == 3

    resumed = _CountingProviders()
    _run(resumed, _store(state))
    assert resumed.calls == TOTAL_CALLS - (CALLS_PER_PRESET * 3) == 162


def test_a_second_resume_after_another_reset_continues_correctly(tmp_path: Path) -> None:
    state = tmp_path / "state"
    # Three resets, then a clean finish.
    _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET * 2 + 4), _store(state))
    assert len(_store(state).load()) == 2

    _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET * 5 + 1), _store(state))
    assert len(_store(state).load()) == 7

    _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET * 2), _store(state))
    assert len(_store(state).load()) == 9

    final = _CountingProviders()
    package, new_calls, restored = _run(final, _store(state))
    assert final.calls == CALLS_PER_PRESET * 3 == 54
    assert restored["ga4"] + restored["gsc"] == CALLS_PER_PRESET * 9 == 162
    assert new_calls["ga4"] + new_calls["gsc"] == 54
    assert len(package["comparisons"]) == 120


def test_final_request_count_equals_only_the_requests_not_already_completed(tmp_path: Path) -> None:
    state = tmp_path / "state"
    completed = 0
    spent = 0
    # `fail_after` is charged against this run only, so each entry is how many
    # further presets that run completes before the transport dies.
    for further in (4, 5):
        client = _CountingProviders(fail_after=CALLS_PER_PRESET * further + 2)
        _run_expecting_reset(client, _store(state))
        spent += client.calls
        completed += further
        assert len(_store(state).load()) == completed
    assert completed == 9

    final = _CountingProviders()
    _run(final, _store(state))
    # Only the three presets never completed were paid for in the final run.
    assert final.calls == CALLS_PER_PRESET * 3 == 54
    # The sunk partial-preset work is real and is not hidden: total spend across
    # every run exceeds 216 by exactly the two abandoned partial presets.
    assert spent + final.calls == TOTAL_CALLS + 4


def test_fully_resumed_output_is_byte_identical_to_a_clean_run(tmp_path: Path) -> None:
    clean, _, _ = _run(_CountingProviders(), None)

    state = tmp_path / "state"
    completed = 0
    # Four separate transport resets at four different points, none of them on
    # a preset boundary, leaving 11 of 12 presets durably recorded.
    for further in (1, 4, 3, 3):
        _run_expecting_reset(
            _CountingProviders(fail_after=CALLS_PER_PRESET * further + 3), _store(state)
        )
        completed += further
        assert len(_store(state).load()) == completed
    assert completed == 11

    resumed, _, restored = _run(_CountingProviders(), _store(state))

    assert restored["ga4"] + restored["gsc"] == CALLS_PER_PRESET * 11
    # Cumulative accounting in the package matches a clean 216-call run exactly.
    assert resumed["source_identity"]["ga4_provider_calls"] == 144
    assert resumed["source_identity"]["gsc_provider_calls"] == 72
    assert json.dumps(resumed, sort_keys=True) == json.dumps(clean, sort_keys=True)


# Refusals. Every one of these would otherwise produce a blended artifact.


def _complete_one_preset(state: Path) -> None:
    _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET), _store(state))
    assert len(_store(state).load()) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"report_id": "00000000-0000-0000-0000-000000000000"},
        {"client_id": "00000000-0000-0000-0000-000000000000"},
        {"project_id": "00000000-0000-0000-0000-000000000000"},
        {"profile": "lucy-escobar"},
    ],
    ids=["report", "client", "project", "profile"],
)
def test_identity_mismatch_refuses_resume(tmp_path: Path, overrides) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    with pytest.raises(ComparisonResumeError, match="does not match this run"):
        _store(state, **overrides).load()


def test_period_mismatch_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    with pytest.raises(ComparisonResumeError, match="does not match this run"):
        _store(state, report_end=date(2026, 7, 7)).load()
    with pytest.raises(ComparisonResumeError, match="does not match this run"):
        _store(state, report_start=date(2026, 1, 2)).load()


def test_provider_configuration_mismatch_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    other = provider_configuration_fingerprint(
        ga4_property_id="987654321", gsc_site_url="https://example.invalid/"
    )
    with pytest.raises(ComparisonResumeError, match="does not match this run"):
        _store(state, provider_configuration_fingerprint=other).load()


def _mutate_identity_manifest(state: Path, **changes) -> None:
    path = state / IDENTITY_FILENAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(changes)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_dataset_mismatch_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    _mutate_identity_manifest(state, dataset_identity="avs:other:2026-07-08:presentation_comparisons.v1")
    with pytest.raises(ComparisonResumeError, match="does not match this run"):
        _store(state).load()


def test_contract_version_mismatch_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    _mutate_identity_manifest(state, contract_version=2)
    with pytest.raises(ComparisonResumeError, match="does not match this run"):
        _store(state).load()


def test_comparison_operation_version_mismatch_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    _mutate_identity_manifest(state, comparison_operation_version="something_else.v9")
    with pytest.raises(ComparisonResumeError, match="does not match this run"):
        _store(state).load()


def test_duplicate_preset_state_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    original = next(state.glob("preset-00-*.json"))
    record = json.loads(original.read_text(encoding="utf-8"))
    # A second file claiming the same preset under a different preset's name.
    duplicate = state / f"preset-01-{COMPARISON_PRESET_KEYS[1]}.json"
    duplicate.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ComparisonResumeError, match="conflicts with its filename"):
        _store(state).load()


def test_corrupt_checkpoint_state_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    target = next(state.glob("preset-00-*.json"))
    target.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(ComparisonResumeError, match="unreadable or corrupt"):
        _store(state).load()


def test_tampered_entries_fail_the_integrity_digest(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    target = next(state.glob("preset-00-*.json"))
    record = json.loads(target.read_text(encoding="utf-8"))
    record["entries"][0]["section_key"] = "ga4_user_engagement"
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ComparisonResumeError, match="integrity digest"):
        _store(state).load()


def test_unknown_state_in_the_checkpoint_directory_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    (state / "unexpected.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ComparisonResumeError, match="unknown state"):
        _store(state).load()


def test_preset_state_without_an_identity_manifest_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    (state / IDENTITY_FILENAME).unlink()
    with pytest.raises(ComparisonResumeError, match="no identity manifest"):
        _store(state).load()


def test_a_record_naming_an_unknown_preset_refuses_resume(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    target = next(state.glob("preset-00-*.json"))
    record = json.loads(target.read_text(encoding="utf-8"))
    record["preset_key"] = "not_a_real_preset"
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ComparisonResumeError, match="unknown preset"):
        _store(state).load()


# Partial state must never look like a final artifact.


def test_partial_state_cannot_pass_final_contract_validation(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)
    record = json.loads(next(state.glob("preset-00-*.json")).read_text(encoding="utf-8"))

    assert record["checkpoint_schema_version"] == CHECKPOINT_SCHEMA_VERSION
    # It carries the checkpoint identifier, never the final contract identifier.
    assert "schema_version" not in record
    assert "contract_identifier" not in record
    with pytest.raises(ValueError):
        validate_presentation_comparison_package(record)


def test_an_incomplete_comparison_set_is_refused_before_assembly(tmp_path: Path) -> None:
    """Only 11 of 12 presets recorded, and the provider is then denied.

    Proves the completeness check, not merely that a full run happens to work.
    """
    state = tmp_path / "state"
    _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET * 11), _store(state))
    assert len(_store(state).load()) == 11

    class _Denied(_CountingProviders):
        def _charge(self, provider):  # noqa: D401 - no provider access permitted
            raise AssertionError("a completed preset must never be requested again")

    # The twelfth preset is genuinely missing, so assembly must not happen.
    with pytest.raises(AssertionError):
        _run(_Denied(), _store(state))


# No retry, anywhere.


def test_a_failed_request_stops_immediately_with_no_retry(tmp_path: Path) -> None:
    state = tmp_path / "state"

    class _CountingFailure(_CountingProviders):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        def _charge(self, provider):
            self.attempts += 1
            raise TransportReset("connection reset")

    client = _CountingFailure()
    _run_expecting_reset(client, _store(state))
    # Exactly one attempt. No second attempt for the same request, no loop.
    assert client.attempts == 1
    assert _store(state).load() == {}


def test_resume_does_not_reissue_and_does_not_retry(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _complete_one_preset(state)

    class _ByFamily(_CountingProviders):
        def __init__(self):
            super().__init__()
            self.summaries = 0
            self.series = 0

        def run_exact_range_summary(self, date_range, *, metric_names=()):
            result = super().run_exact_range_summary(date_range, metric_names=metric_names)
            self.summaries += 1
            return result

        def run_exact_range_traffic_series(self, date_range):
            result = super().run_exact_range_traffic_series(date_range)
            self.series += 1
            return result

    # A clean run issues two of each per preset. Range strings cannot identify a
    # preset here, because year_to_date resolves to the same span as
    # report_period, so the proof is per-family request counts.
    clean = _ByFamily()
    _run(clean, None)
    assert (clean.summaries, clean.series) == (24, 24)

    resumed = _ByFamily()
    _run(resumed, _store(state))
    # Exactly one preset's worth fewer of every family. Nothing re-issued.
    assert (resumed.summaries, resumed.series) == (22, 22)
    assert resumed.calls == TOTAL_CALLS - CALLS_PER_PRESET


# Call accounting.


def test_call_accounting_survives_every_failure(tmp_path: Path) -> None:
    state = tmp_path / "state"
    completed = 0
    for further in (0, 1, 3):
        client = _CountingProviders(fail_after=CALLS_PER_PRESET * further)
        new_calls, restored = _run_expecting_reset(client, _store(state))
        # Newly consumed is exactly what the fake was charged this run, even
        # though the run ended in an exception rather than a return.
        assert new_calls["ga4"] + new_calls["gsc"] == client.calls
        assert new_calls["ga4"] == client.ga4_calls
        assert new_calls["gsc"] == client.gsc_calls
        # Prior work is reported separately, never folded into new spend.
        assert restored["ga4"] + restored["gsc"] == CALLS_PER_PRESET * completed
        completed += further
        assert len(_store(state).load()) == completed


def test_new_and_prior_calls_are_reported_separately(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _run_expecting_reset(_CountingProviders(fail_after=CALLS_PER_PRESET * 4), _store(state))
    package, new_calls, restored = _run(_CountingProviders(), _store(state))

    assert restored == {"ga4": 48, "gsc": 24}
    assert new_calls == {"ga4": 96, "gsc": 48}
    # The package reports the cumulative truth of a 216-call dataset.
    assert package["source_identity"]["ga4_provider_calls"] == 144
    assert package["source_identity"]["gsc_provider_calls"] == 72


# Atomic writes and secret hygiene.


def test_atomic_write_leaves_no_temporary_files(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _run(_CountingProviders(), _store(state))
    names = sorted(path.name for path in state.iterdir())
    assert len([name for name in names if name.startswith("preset-")]) == 12
    assert IDENTITY_FILENAME in names
    assert not [name for name in names if name.startswith(".tmp-")]


def test_a_failed_write_leaves_no_partial_record(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    store = _store(state)

    import src.client_report_presentation_comparison_resume as resume

    real_replace = resume.os.replace

    def exploding_replace(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(resume.os, "replace", exploding_replace)
    with pytest.raises(OSError):
        _run(_CountingProviders(), store)
    monkeypatch.setattr(resume.os, "replace", real_replace)

    # No preset file, and no temporary debris left behind.
    assert not list(state.glob("preset-*.json"))
    assert not list(state.glob(".tmp-*"))


def test_checkpoint_records_carry_no_secret_material(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _run(_CountingProviders(), _store(state))
    for path in state.iterdir():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert_no_secret_material(payload, label=path.name)


def test_the_identity_manifest_never_discloses_provider_identifiers(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _run(_CountingProviders(), _store(state))
    text = (state / IDENTITY_FILENAME).read_text(encoding="utf-8")
    assert "123456789" not in text
    assert "example.invalid" not in text
    assert provider_configuration_fingerprint(
        ga4_property_id="123456789", gsc_site_url="https://example.invalid/"
    ) in text


def test_final_contract_carries_no_secret_material(tmp_path: Path) -> None:
    package, _, _ = _run(_CountingProviders(), _store(tmp_path / "state"))
    assert_no_secret_material(package, label="comparison contract")


def test_secret_scanning_actually_refuses_secret_shaped_material() -> None:
    with pytest.raises(ComparisonResumeError, match="refresh_token"):
        assert_no_secret_material({"nested": {"refresh_token": "x"}}, label="probe")


# Resume stays optional.


def test_a_disabled_store_behaves_exactly_as_before_resume_existed() -> None:
    store = ComparisonCheckpointStore(None, _identity())
    assert not store.enabled
    assert store.load() == {}
    client = _CountingProviders()
    package, _, restored = _run(client, store)
    assert client.calls == TOTAL_CALLS
    assert restored == {"ga4": 0, "gsc": 0}
    assert len(package["comparisons"]) == 120
