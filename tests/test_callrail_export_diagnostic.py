import csv

from src.dashboard_lab.callrail_export_diagnostic import (
    diagnose_callrail_export_shape,
    diagnostic_to_lines,
)


HEADERS = [
    "Call Status",
    "Company Name",
    "Company ID",
    "Number Name",
    "Tracking Number",
    "Name",
    "Phone Number",
    "Email",
    "First-Time Caller",
    "City",
    "State",
    "Country",
    "Agent Name",
    "Agent Number",
    "Source",
    "Duration (seconds)",
    "Start Time",
    "Device Type",
    "Keywords",
    "Referrer",
    "Medium",
    "Landing Page",
    "Campaign",
    "Value",
    "Tags",
    "Qualified",
    "Destination Number",
    "Browser",
    "Google Ads gclid",
    "Facebook fbclid",
    "Keywords Spotted",
    "Call Highlights",
    "Match Type",
    "Ad Group",
    "Ad Position",
    "utm_medium",
    "utm_source",
    "Customer Talk Time Percent",
    "Agent Talk Time Percent",
    "Active Page",
    "Recording Url",
    "Note",
]


def test_diagnostic_detects_known_headers_and_sensitive_headers(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        HEADERS,
        [
            {
                "Call Status": "Answered",
                "Tracking Number": "+1 555 111 2222",
                "Name": "Synthetic Caller",
                "Phone Number": "555-222-3333",
                "Email": "person@example.test",
                "Recording Url": "https://recordings.example.test/call/1",
                "Note": "private follow-up note",
                "Keywords": "oceanfront hotel",
                "Campaign": "Brand Search",
                "Landing Page": "https://example.test/rooms?email=person@example.test",
                "Source": "Google Ads",
                "Medium": "cpc",
                "Duration (seconds)": "64",
                "Qualified": "Yes",
            }
        ],
    )

    diagnostic = diagnose_callrail_export_shape(csv_path, profile="inn-at-spanish-head")

    assert diagnostic.parsed_successfully is True
    assert diagnostic.row_count == 1
    assert diagnostic.missing_expected_headers == []
    assert "Tracking Number" in diagnostic.sensitive_headers_detected
    assert "Recording Url" in diagnostic.sensitive_headers_detected
    assert diagnostic.mapping_readiness["keyword_field_present"] is True
    assert diagnostic.mapping_readiness["medium_or_utm_or_gclid_fields_present"] is True


def test_diagnostic_reports_missing_expected_headers(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        ["Call Status", "Keywords"],
        [{"Call Status": "Answered", "Keywords": "synthetic keyword"}],
    )

    diagnostic = diagnose_callrail_export_shape(csv_path)

    assert "Campaign" in diagnostic.missing_expected_headers
    assert "Landing Page" in diagnostic.missing_expected_headers
    assert diagnostic.mapping_readiness["campaign_field_present"] is False


def test_diagnostic_counts_presence_and_google_ads_attribution(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        HEADERS,
        [
            {
                "Call Status": "Answered",
                "Keywords": "oceanfront hotel",
                "Campaign": "Brand Search",
                "Landing Page": "/rooms",
                "Google Ads gclid": "synthetic-gclid",
                "Duration (seconds)": "120",
                "Qualified": "Yes",
            },
            {
                "Call Status": "Missed",
                "Campaign": "Generic Search",
                "Landing Page": "/offers",
                "utm_source": "google",
                "utm_medium": "paid_search",
            },
            {
                "Keywords": "coastal lodging",
                "Source": "paid search",
                "Medium": "cpc",
                "Duration (seconds)": "35",
            },
            {
                "Source": "organic",
            },
        ],
    )

    diagnostic = diagnose_callrail_export_shape(csv_path)

    assert diagnostic.aggregate_counts["total_rows"] == 4
    assert diagnostic.aggregate_counts["rows_with_keyword_present"] == 2
    assert diagnostic.aggregate_counts["rows_without_keyword"] == 2
    assert diagnostic.aggregate_counts["rows_with_campaign_present"] == 2
    assert diagnostic.aggregate_counts["rows_with_landing_page_present"] == 2
    assert diagnostic.aggregate_counts["rows_with_gclid_present"] == 1
    assert diagnostic.aggregate_counts["rows_likely_google_ads_attributed"] == 3
    assert diagnostic.aggregate_counts["rows_with_qualified_value_present"] == 1
    assert diagnostic.aggregate_counts["rows_with_duration_present"] == 2
    assert diagnostic.aggregate_counts["rows_with_call_status_present"] == 2


def test_diagnostic_redacts_phone_and_email_looking_top_values(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        ["Keywords", "Campaign", "Source", "Medium"],
        [
            {
                "Keywords": "call 555-222-3333",
                "Campaign": "person@example.test",
                "Source": "Google Ads",
                "Medium": "cpc",
            }
        ],
    )

    output = "\n".join(diagnostic_to_lines(diagnose_callrail_export_shape(csv_path)))

    assert "555-222-3333" not in output
    assert "person@example.test" not in output
    assert "[redacted]" in output


def test_diagnostic_strips_query_strings_from_landing_page_examples(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        ["Landing Page"],
        [{"Landing Page": "https://example.test/rooms?phone=5552223333&utm_source=google"}],
    )

    diagnostic = diagnose_callrail_export_shape(csv_path)

    assert diagnostic.top_examples["landing_pages"] == [("/rooms", 1)]


def test_diagnostic_reports_safe_qualified_value_counts(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        ["Qualified", "Name", "Phone Number"],
        [
            {"Qualified": "Yes", "Name": "Private Caller", "Phone Number": "555-222-3333"},
            {"Qualified": "No", "Name": "Other Caller", "Phone Number": "555-333-4444"},
            {"Qualified": "Yes", "Name": "Third Caller", "Phone Number": "555-444-5555"},
            {"Qualified": "", "Name": "Fourth Caller", "Phone Number": "555-555-6666"},
        ],
    )

    diagnostic = diagnose_callrail_export_shape(csv_path)
    output = "\n".join(diagnostic_to_lines(diagnostic))

    assert diagnostic.qualified_value_counts == [("Yes", 2), ("No", 1), ("blank", 1)]
    assert "Qualified value counts:" in output
    assert "Yes: 2" in output
    assert "No: 1" in output
    assert "Private Caller" not in output
    assert "555-222-3333" not in output


def test_diagnostic_redacts_personal_identifier_landing_page_examples(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        ["Landing Page"],
        [{"Landing Page": "https://example.test/customers/jane-doe"}],
    )

    diagnostic = diagnose_callrail_export_shape(csv_path)

    assert diagnostic.top_examples["landing_pages"] == [("[redacted]", 1)]


def test_diagnostic_output_excludes_sensitive_raw_values_and_writes_no_fixture(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        HEADERS,
        [
            {
                "Name": "Sensitive Synthetic Name",
                "Phone Number": "555-444-1212",
                "Email": "private@example.test",
                "Tracking Number": "555-000-9999",
                "Destination Number": "555-888-7777",
                "Recording Url": "https://recording.example.test/private",
                "Note": "private note text",
                "Call Highlights": "private call detail",
                "Keywords Spotted": "private keyword spotted text",
                "Referrer": "https://referrer.example.test/private",
                "Active Page": "https://example.test/private",
                "Keywords": "safe aggregate keyword",
                "Campaign": "Safe Aggregate Campaign",
            }
        ],
    )

    output = "\n".join(diagnostic_to_lines(diagnose_callrail_export_shape(csv_path)))

    assert "Sensitive Synthetic Name" not in output
    assert "555-444-1212" not in output
    assert "private@example.test" not in output
    assert "https://recording.example.test/private" not in output
    assert "private note text" not in output
    assert "private call detail" not in output
    assert "private keyword spotted text" not in output
    assert "safe aggregate keyword" in output
    assert not (tmp_path / "callrail-summary.json").exists()


def _write_csv(tmp_path, headers, rows):
    path = tmp_path / "calls.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})
    return path
