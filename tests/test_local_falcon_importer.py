import json
import subprocess
import sys
from pathlib import Path

from src.local_falcon_importer import (
    derive_data_point_counts,
    import_local_falcon_csv,
    normalize_competitors,
    normalize_grid_points,
    normalize_rank,
    parse_ai_analysis,
    rank_status,
    validate_local_falcon_summary,
)


def _write(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _scan_report(tmp_path, keyword="service keyword"):
    return _write(
        tmp_path / "scan-report.csv",
        f"""
Keyword,Scan Date,Grid Size,Radius Miles,Center Latitude,Center Longitude,Business Name,Business Address,Rating,Reviews,ARP,ATRP,SoLV
{keyword},2026-05-12T13:52:00,21x21,10,45.0,-122.0,Demo Clinic,123 Demo Ave,4.8,120,11.7,17.9,6.17
""",
    )


def _data_points(tmp_path):
    return _write(
        tmp_path / "data-points.csv",
        """
Latitude,Longitude,Rank,Zone,Location,Competitor Name,Competitor Rank,SoLV,ARP,ATRP,Rating,Reviews,Category,Address
45.02,-122.02,1,NW,Point A,Strong Demo Competitor,1,15.5,4.2,8.1,4.9,240,Demo Service,1 Example Way
45.02,-122.00,5,N,Point B,Strong Demo Competitor,2,15.5,4.2,8.1,4.9,240,Demo Service,1 Example Way
45.02,-121.98,20+,NE,Point C,Watch Demo Competitor,4,8.2,8.0,12.1,4.7,90,Demo Service,2 Example Way
45.00,-122.02,,W,Point D,Vulnerable Demo Competitor,18,2.1,16.0,20.5,4.1,25,Demo Service,3 Example Way
45.00,-122.00,13,Center,Point E,Demo Clinic,3,6.0,10.0,11.0,4.8,120,Demo Service,123 Demo Ave
45.00,-121.98,20 +,E,Point F,Watch Demo Competitor,8,8.2,8.0,12.1,4.7,90,Demo Service,2 Example Way
44.98,-122.02,2,SW,Point G,Strong Demo Competitor,1,15.5,4.2,8.1,4.9,240,Demo Service,1 Example Way
44.98,-122.00,9,S,Point H,Watch Demo Competitor,7,8.2,8.0,12.1,4.7,90,Demo Service,2 Example Way
44.98,-121.98,not found,SE,Point I,Other Demo Competitor,22,0.5,20.0,25.0,3.9,10,Demo Service,4 Example Way
""",
    )


def _data_points_with_ranks(tmp_path, ranks):
    rows = [
        "Latitude,Longitude,Rank,Zone,Location,Competitor Name,Competitor Rank,SoLV,ARP,ATRP,Rating,Reviews,Category,Address"
    ]
    for index, rank in enumerate(ranks):
        row = index // 3
        col = index % 3
        rank_text = "" if rank is None else str(rank)
        competitor = "Demo Clinic" if index == 0 else f"Competitor {index}"
        rows.append(
            f"{45.02 - row * 0.01},{-122.02 + col * 0.01},{rank_text},Zone {index},Point {index},{competitor},{index + 1},10,5,9,4.{index},10,Demo Service,{index} Example Way"
        )
    return _write(tmp_path / "data-points.csv", "\n".join(rows))


def test_rank_normalization_and_status():
    assert normalize_rank("1") == 1
    assert normalize_rank("20 +") == "20+"
    assert normalize_rank("23") == "20+"
    assert normalize_rank("") is None
    assert rank_status(2) == "top_3"
    assert rank_status(7) == "top_10"
    assert rank_status(14) == "top_20"
    assert rank_status("20+") == "weak"
    assert rank_status(None) == "not_found"


def test_grid_points_and_counts_derive_from_coordinates(tmp_path):
    points = normalize_grid_points(_csv_rows(_data_points(tmp_path)))
    counts = derive_data_point_counts(points)

    assert points[0]["row"] == 0
    assert points[0]["col"] == 0
    assert points[-1]["row"] == 2
    assert points[-1]["col"] == 2
    assert points[2]["rank"] == "20+"
    assert points[3]["status"] == "not_found"
    assert counts == {
        "total": 9,
        "found": 5,
        "top_3": 2,
        "top_10": 4,
        "top_20": 5,
        "not_found_or_20_plus": 4,
    }


def test_grouped_local_falcon_result_rows_derive_client_grid_points():
    rows = [
        {
            "data point id": "1",
            "latitude": "45.2",
            "longitude": "-122.2",
            "rank": "1",
            "business": "Other Demo Business",
        },
        {
            "data point id": "1",
            "latitude": "45.2",
            "longitude": "-122.2",
            "rank": "8",
            "business": "Demo Clinic",
        },
        {
            "data point id": "2",
            "latitude": "45.2",
            "longitude": "-122.1",
            "rank": "1",
            "business": "Other Demo Business",
        },
        {
            "data point id": "3",
            "latitude": "45.1",
            "longitude": "-122.2",
            "rank": "3",
            "business": "Demo Clinic",
        },
        {
            "data point id": "4",
            "latitude": "45.1",
            "longitude": "-122.1",
            "rank": "1",
            "business": "Other Demo Business",
        },
    ]

    points = normalize_grid_points(rows, "Demo Clinic")
    counts = derive_data_point_counts(points)

    assert len(points) == 4
    assert points[0]["rank"] == 8
    assert points[1]["status"] == "not_found"
    assert points[2]["status"] == "top_3"
    assert {point["row"] for point in points} == {0, 1}
    assert {point["col"] for point in points} == {0, 1}
    assert counts["total"] == 4
    assert counts["found"] == 2
    assert counts["top_10"] == 2
    assert counts["not_found_or_20_plus"] == 2


def test_import_writes_local_falcon_summary_v2_with_competitors_and_ai(tmp_path):
    ai = _write(
        tmp_path / "ai-analysis.txt",
        """
Summary:
The scan shows uneven visibility.

Issues:
- Western grid points need stronger relevance.

Recommendations:
- Add local proof and supporting internal links.
""",
    )
    output = tmp_path / "exports" / "local-real" / "dashboard-lab" / "demo-profile" / "local-falcon-summary.json"

    result = import_local_falcon_csv(
        profile="demo-profile",
        keyword="service keyword",
        scan_report_path=_scan_report(tmp_path),
        data_points_path=_data_points(tmp_path),
        ai_analysis_path=ai,
        output_path=output,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    scan = payload["keyword_scans"][0]

    assert result.competitor_count == 5
    assert payload["schema_version"] == "local_falcon_summary.v2"
    assert payload["provider"] == "local_falcon"
    assert payload["real_data"] is True
    assert payload["summary"]["keyword_count"] == 1
    assert scan["id"] == "service-keyword"
    assert scan["grid_size_label"] == "21x21"
    assert scan["rendered_grid"] == {"rows": 3, "columns": 3}
    assert scan["data_points"]["top_10"] == 4
    assert scan["local_falcon_metrics"] == {"arp": 11.7, "atrp": 17.9, "solv": 6.17}
    assert scan["competitors"][0]["relationship"] == "market_leader"
    assert any(item["relationship"] == "client" for item in scan["competitors"])
    assert scan["ai_analysis"]["available"] is True
    assert scan["ai_analysis"]["issues"] == ["Western grid points need stronger relevance."]
    assert scan["action_bridge"]


def test_import_preserves_and_updates_existing_keyword_scans(tmp_path):
    output = tmp_path / "local-falcon-summary.json"
    first_points = _data_points(tmp_path)
    import_local_falcon_csv(
        profile="demo-profile",
        keyword="first keyword",
        scan_report_path=_scan_report(tmp_path, "first keyword"),
        data_points_path=first_points,
        output_path=output,
        featured_keyword_id="first-keyword",
    )
    import_local_falcon_csv(
        profile="demo-profile",
        keyword="second keyword",
        scan_report_path=_scan_report(tmp_path, "second keyword"),
        data_points_path=first_points,
        output_path=output,
    )
    import_local_falcon_csv(
        profile="demo-profile",
        keyword="first keyword",
        scan_report_path=_scan_report(tmp_path, "first keyword"),
        data_points_path=first_points,
        output_path=output,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    ids = [scan["id"] for scan in payload["keyword_scans"]]

    assert ids.count("first-keyword") == 1
    assert sorted(ids) == ["first-keyword", "second-keyword"]
    assert payload["summary"]["keyword_count"] == 2
    assert payload["summary"]["featured_keyword_id"] == "first-keyword"


def test_multi_keyword_summary_uses_data_point_coverage_for_strongest_and_weakest(tmp_path):
    output = tmp_path / "local-falcon-summary.json"
    cases = [
        ("weak keyword", [11, 12, 13, None, None, "20+", None, "20+", None]),
        ("wide keyword", [4, 5, 6, 7, 8, 9, 10, 11, None]),
        ("strong keyword", [1, 2, 3, 4, 5, 6, 7, 8, 9]),
    ]

    for name, ranks in cases:
        folder = tmp_path / name.replace(" ", "-")
        folder.mkdir()
        import_local_falcon_csv(
            profile="demo-profile",
            keyword=name,
            business_name="Demo Clinic",
            scan_report_path=_scan_report(folder, name),
            data_points_path=_data_points_with_ranks(folder, ranks),
            output_path=output,
        )

    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["summary"]["keyword_count"] == 3
    assert payload["summary"]["strongest_keyword_id"] == "strong-keyword"
    assert payload["summary"]["weakest_keyword_id"] == "weak-keyword"


def test_explicit_featured_keyword_override(tmp_path):
    output = tmp_path / "local-falcon-summary.json"
    import_local_falcon_csv(
        profile="demo-profile",
        keyword="first keyword",
        scan_report_path=_scan_report(tmp_path, "first keyword"),
        data_points_path=_data_points(tmp_path),
        output_path=output,
        featured_keyword_id="first-keyword",
    )
    import_local_falcon_csv(
        profile="demo-profile",
        keyword="second keyword",
        scan_report_path=_scan_report(tmp_path, "second keyword"),
        data_points_path=_data_points(tmp_path),
        output_path=output,
        featured_keyword_id="second-keyword",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["summary"]["featured_keyword_id"] == "second-keyword"


def test_validate_local_falcon_summary_reports_per_keyword_details(tmp_path):
    output = tmp_path / "local-falcon-summary.json"
    import_local_falcon_csv(
        profile="demo-profile",
        keyword="service keyword",
        scan_report_path=_scan_report(tmp_path),
        data_points_path=_data_points(tmp_path),
        output_path=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    validation = validate_local_falcon_summary(payload, output)

    assert validation.profile == "demo-profile"
    assert validation.keyword_scan_count == 1
    assert validation.keyword_summaries[0]["keyword"] == "service keyword"
    assert validation.keyword_summaries[0]["total"] == 9
    assert validation.keyword_summaries[0]["competitor_count"] == 5
    assert any("AI analysis is missing" in warning for warning in validation.warnings)


def test_batch_manifest_imports_multiple_keyword_exports(tmp_path):
    output = tmp_path / "out" / "local-falcon-summary.json"
    manifest = {
        "profile": "demo-profile",
        "business_name": "Demo Clinic",
        "output": "out/local-falcon-summary.json",
        "featured_keyword_id": "wide-keyword",
        "keywords": [],
    }
    for name, ranks in [
        ("strong keyword", [1, 2, 3, 4, 5, 6, 7, 8, 9]),
        ("wide keyword", [4, 5, 6, 7, 8, 9, 10, 11, None]),
    ]:
        folder = tmp_path / "local-falcon-exports" / "demo-profile" / name.replace(" ", "-")
        folder.mkdir(parents=True)
        _scan_report(folder, name)
        _data_points_with_ranks(folder, ranks)
        manifest["keywords"].append(
            {
                "keyword": name,
                "scan_report": f"local-falcon-exports/demo-profile/{name.replace(' ', '-')}/scan-report.csv",
                "data_points": f"local-falcon-exports/demo-profile/{name.replace(' ', '-')}/data-points.csv",
            }
        )
    manifest_path = tmp_path / "local-falcon-manifests" / "demo-profile.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "import_local_falcon_batch.py"),
            "--manifest",
            str(manifest_path),
            "--overwrite",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["keyword_count"] == 2
    assert payload["summary"]["featured_keyword_id"] == "wide-keyword"
    assert "Keyword scans: 2" in completed.stdout


def test_competitor_normalization_uses_explicit_summary_metrics():
    rows = [
        {
            "business": "Summary Competitor",
            "rank": "2",
            "found points": "21",
            "top 3 points": "12",
            "top 10 points": "18",
            "solv": "14.8",
        }
    ]

    competitors = normalize_competitors(rows, client_business_name=None)

    assert competitors[0]["found_points"] == 21
    assert competitors[0]["top_3_points"] == 12
    assert competitors[0]["top_10_points"] == 18
    assert competitors[0]["relationship"] == "market_leader"


def test_ai_analysis_optional_behavior():
    assert parse_ai_analysis(None) == {"available": False}
    parsed = parse_ai_analysis("Summary:\nShort local scan note.")
    assert parsed["available"] is True
    assert parsed["summary"] == "Short local scan note."


def _csv_rows(path):
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {
                key.lower().replace(" ", " "): (value or "").strip()
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]
