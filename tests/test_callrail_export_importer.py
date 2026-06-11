import csv
import json

import pytest

from src.dashboard_lab.callrail_export_importer import CallRailExportImportError, import_callrail_export
from src.dashboard_lab.paid_callrail_validators import validate_callrail_summary


HEADERS = [
    "Call Status",
    "Number Name",
    "Tracking Number",
    "Name",
    "Phone Number",
    "Email",
    "First-Time Caller",
    "Source",
    "Duration (seconds)",
    "Start Time",
    "Keywords",
    "Referrer",
    "Medium",
    "Landing Page",
    "Campaign",
    "Qualified",
    "Destination Number",
    "Google Ads gclid",
    "Recording Url",
    "Note",
    "utm_medium",
    "utm_source",
]


def test_imports_valid_synthetic_callrail_csv_to_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = _write_csv(
        tmp_path,
        [
            _row(
                status="Answered",
                keyword="oceanfront hotel",
                campaign="Brand Search",
                landing_page="https://example.test/rooms?utm_source=google",
                gclid="synthetic-gclid-1",
                duration="100",
                first_time="Yes",
                qualified="Qualified",
                start_time="2026-01-15 10:00:00",
                number_name="Booking line",
            ),
            _row(
                status="Missed",
                keyword="oceanfront hotel",
                campaign="Brand Search",
                landing_page="https://example.test/rooms?utm_source=google",
                gclid="synthetic-gclid-2",
                duration="50",
                first_time="No",
                qualified="No",
                start_time="2026-01-20 10:00:00",
                number_name="Booking line",
            ),
            _row(
                status="Completed",
                keyword="lincoln city lodging",
                campaign="Generic Search",
                landing_page="https://example.test/offers?private=value",
                duration="200",
                first_time="first time",
                qualified="true",
                start_time="2026-02-03",
                number_name="Deals line",
                utm_source="google",
                utm_medium="cpc",
            ),
        ],
    )

    result = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        start_date="2026-01-01",
        end_date="2026-02-28",
        real_output=True,
    )

    payload = result.payload
    validate_callrail_summary(payload)
    assert result.output_path.as_posix() == "exports/local-real/dashboard-lab/inn-at-spanish-head/callrail-summary.json"
    assert result.output_path.exists()
    assert payload["schema_version"] == "callrail_summary.v1"
    assert payload["source"] == "local_export"
    assert payload["is_real_data"] is True
    assert payload["profile"] == "inn-at-spanish-head"
    assert payload["client_label"] == "Spanish Head"
    assert payload["summary"]["total_calls"] == 3
    assert payload["summary"]["google_ads_calls"] == 3
    assert payload["summary"]["first_time_callers"] == 2
    assert payload["summary"]["qualified_calls"] == 2
    assert payload["summary"]["answered_calls"] == 2
    assert payload["summary"]["missed_calls"] == 1
    assert payload["summary"]["avg_duration_seconds"] == pytest.approx(116.67)
    assert payload["summary"]["calls_with_keyword_attribution"] == 3
    assert payload["summary"]["calls_without_keyword_attribution"] == 0
    assert json.loads(result.output_path.read_text(encoding="utf-8"))["summary"]["total_calls"] == 3


def test_importer_aggregates_keyword_campaign_and_landing_page_rows(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(keyword="oceanfront hotel", campaign="Brand Search", landing_page="/rooms?a=1", gclid="a"),
            _row(keyword="oceanfront hotel", campaign="Brand Search", landing_page="/rooms?b=2", gclid="b"),
            _row(keyword="hotel deals", campaign="Deals", landing_page="/deals", status="Missed", gclid="c"),
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    keyword_row = payload["keyword_rows"][0]
    assert keyword_row["keyword"] == "oceanfront hotel"
    assert keyword_row["campaign"] == "Brand Search"
    assert keyword_row["landing_page"] == "/rooms"
    assert keyword_row["calls"] == 2
    assert payload["campaign_rows"][0]["campaign"] == "Brand Search"
    assert payload["campaign_rows"][0]["calls"] == 2
    assert payload["landing_page_rows"][0]["landing_page"] == "/rooms"
    assert payload["landing_page_rows"][0]["calls"] == 2


def test_importer_counts_google_ads_by_utm_and_gclid(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(gclid="synthetic-gclid"),
            _row(utm_source="google", utm_medium="paid_search"),
            _row(source="organic", medium="organic", keyword="organic keyword"),
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    assert payload["summary"]["google_ads_calls"] == 2
    assert payload["paid_search_attribution"]["google_ads_calls"] == 2


def test_importer_strips_landing_page_queries_and_excludes_sensitive_values(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(
                keyword="safe keyword",
                campaign="Safe Campaign",
                landing_page="https://example.test/rooms?phone=5552223333&email=person@example.test",
                tracking_number="555-111-2222",
                name="Private Caller",
                phone="555-333-4444",
                email="private@example.test",
                recording_url="https://recordings.example.test/private",
                note="private note",
                gclid="synthetic-gclid",
            )
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload
    output = json.dumps(payload, sort_keys=True)

    assert "https://example.test/rooms?" not in output
    assert "https://example.test/rooms" not in output
    assert '"/rooms"' in output
    assert "555-111-2222" not in output
    assert "Private Caller" not in output
    assert "555-333-4444" not in output
    assert "private@example.test" not in output
    assert "https://recordings.example.test/private" not in output
    assert "private note" not in output


def test_importer_builds_tracking_rows_from_number_name_only(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(number_name="Booking line", tracking_number="555-111-2222", gclid="a"),
            _row(number_name="Booking line", tracking_number="555-111-2222", status="Missed", gclid="b"),
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    assert payload["tracking_number_rows"] == [
        {
            "tracking_number_label": "Booking line",
            "source": "Google Ads",
            "calls": 2,
            "answered_calls": 1,
            "missed_calls": 1,
            "first_time_callers": 0,
        }
    ]


def test_importer_aggregates_duplicate_tracking_labels_across_sources(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(number_name="Website pool", source="Google Ads", medium="cpc", gclid="a"),
            _row(number_name="Website pool", source="", medium="", status="Missed"),
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    assert payload["tracking_number_rows"] == [
        {
            "tracking_number_label": "Website pool",
            "source": "Mixed sources",
            "calls": 2,
            "answered_calls": 1,
            "missed_calls": 1,
            "first_time_callers": 0,
        }
    ]


def test_importer_qualified_parser_counts_truthy_and_false_values(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(qualified="Yes"),
            _row(qualified="call qualified"),
            _row(qualified="good lead"),
            _row(qualified="converted"),
            _row(qualified="2"),
            _row(qualified="No"),
            _row(qualified="not qualified"),
            _row(qualified="0"),
            _row(qualified="maybe"),
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    assert payload["summary"]["qualified_calls"] == 5
    assert any(
        "Qualified field values observed:" in note and "maybe=1" in note and "not qualified=1" in note
        for note in payload["data_quality_notes"]
    )


def test_importer_normalizes_keyword_match_type_wrappers(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(keyword="[spanish hotel oregon]", campaign="Brand Search", gclid="a"),
            _row(keyword='"the inn at spanish head oregon"', campaign="Brand Search", gclid="b"),
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    keywords = {row["keyword"] for row in payload["keyword_rows"]}
    assert "spanish hotel oregon" in keywords
    assert "the inn at spanish head oregon" in keywords
    assert "[spanish hotel oregon]" not in keywords
    assert payload["paid_search_attribution"]["top_keyword"] == "spanish hotel oregon"
    assert any("Keyword display values were normalized" in note for note in payload["data_quality_notes"])


def test_importer_normalizes_landing_page_urls_to_paths(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            _row(
                landing_page="https://spanishhead.com/accommodations/rooms-suites/?utm_source=google#booking",
                gclid="a",
            )
        ],
    )

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    assert payload["landing_page_rows"][0]["landing_page"] == "/accommodations/rooms-suites/"
    assert payload["keyword_rows"][0]["landing_page"] == "/accommodations/rooms-suites/"


def test_importer_uses_consistent_unattributed_source_label(tmp_path):
    csv_path = _write_csv(tmp_path, [_row(source="", medium="", gclid="")])

    payload = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    ).payload

    assert payload["source_rows"][0]["source"] == "Unattributed source"
    assert any("1 call did not include source attribution." == note for note in payload["data_quality_notes"])


def test_importer_refuses_non_local_real_output(tmp_path):
    csv_path = _write_csv(tmp_path, [_row()])

    with pytest.raises(CallRailExportImportError, match="exports/dashboard-lab"):
        import_callrail_export(
            profile="inn-at-spanish-head",
            input_path=csv_path,
            output_root="exports/dashboard-lab",
            real_output=True,
        )


def test_importer_requires_real_output_for_write(tmp_path):
    csv_path = _write_csv(tmp_path, [_row()])

    with pytest.raises(CallRailExportImportError, match="--real-output"):
        import_callrail_export(
            profile="inn-at-spanish-head",
            input_path=csv_path,
        )


def test_importer_dry_run_does_not_write_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = _write_csv(tmp_path, [_row(gclid="synthetic-gclid")])

    result = import_callrail_export(
        profile="inn-at-spanish-head",
        input_path=csv_path,
        real_output=True,
        dry_run=True,
    )

    assert not result.output_path.exists()


def _row(
    *,
    status="Answered",
    number_name="",
    tracking_number="",
    name="",
    phone="",
    email="",
    first_time="No",
    source="Google Ads",
    medium="cpc",
    duration="30",
    start_time="2026-01-01 09:00:00",
    keyword="oceanfront hotel",
    referrer="",
    landing_page="/rooms",
    campaign="Brand Search",
    qualified="No",
    destination_number="",
    gclid="",
    recording_url="",
    note="",
    utm_medium="",
    utm_source="",
):
    return {
        "Call Status": status,
        "Number Name": number_name,
        "Tracking Number": tracking_number,
        "Name": name,
        "Phone Number": phone,
        "Email": email,
        "First-Time Caller": first_time,
        "Source": source,
        "Duration (seconds)": duration,
        "Start Time": start_time,
        "Keywords": keyword,
        "Referrer": referrer,
        "Medium": medium,
        "Landing Page": landing_page,
        "Campaign": campaign,
        "Qualified": qualified,
        "Destination Number": destination_number,
        "Google Ads gclid": gclid,
        "Recording Url": recording_url,
        "Note": note,
        "utm_medium": utm_medium,
        "utm_source": utm_source,
    }


def _write_csv(tmp_path, rows):
    path = tmp_path / "calls.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path
