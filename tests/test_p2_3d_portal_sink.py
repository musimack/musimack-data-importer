import json
import urllib.error

import pytest

from src.cloud_ingestion.domain import IngestionConfiguration, RunRequest
from src.cloud_ingestion.errors import SinkError
from src.cloud_ingestion.portal_sink import PortalIngestionSink


class Tokens:
    def __init__(self):
        self.audiences = []

    def token_for_audience(self, audience):
        self.audiences.append(audience)
        return "header.payload.signature"


def values():
    request = RunRequest(
        project_id="20000000-0000-0000-0000-000000000001",
        provider="ga4",
        week_start=__import__("datetime").date(2026, 7, 27),
        idempotency_key="30000000-0000-0000-0000-000000000001",
        environment="production",
    )
    config = IngestionConfiguration(
        identity="pilot",
        version=1,
        client_id="10000000-0000-0000-0000-000000000001",
        project_id=request.project_id,
        project_slug="pilot",
        provider="ga4",
        environment="production",
        reporting_timezone="America/Los_Angeles",
        external_resource_type="ga4_property",
        external_resource_id="properties/999999999",
        credential_binding_key="fixture/pilot",
        request_ceiling=1,
        enabled=True,
    )
    return request, config


def test_sink_uses_same_exact_audience_token_for_both_layers(monkeypatch):
    captured = {}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, _): return json.dumps({"accepted": True, "outcome": "accepted"}).encode()

    def urlopen(request, timeout):
        captured["request"] = request
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    tokens = Tokens()
    sink = PortalIngestionSink("https://portal.example", tokens)
    request, config = values()
    receipt = sink.begin(request, config)
    sink.complete(receipt, {"metrics": [{"value": 1}]})
    sent = captured["request"]
    assert tokens.audiences == ["https://portal.example"]
    assert sent.headers["Authorization"] == "Bearer header.payload.signature"
    assert sent.headers["X-serverless-authorization"] == "Bearer header.payload.signature"
    envelope = json.loads(sent.data)
    assert envelope["workload"] == {"environment": "production"}
    assert envelope["resource"]["identity"] == "properties/999999999"


def test_sink_refuses_non_https_or_wildcard_urls():
    with pytest.raises(SinkError):
        PortalIngestionSink("http://portal.example", Tokens())
    with pytest.raises(SinkError):
        PortalIngestionSink("https://*.example", Tokens())


def test_sink_replay_and_invalid_contract_proofs_reuse_in_memory_payload(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status, payload):
            self.status = status
            self.payload = payload

        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, _): return json.dumps(self.payload).encode()

    responses = [
        Response(200, {"accepted": True, "outcome": "accepted", "revision_id": "r1"}),
        Response(200, {"accepted": True, "outcome": "replayed", "revision_id": "r1"}),
        Response(422, {"accepted": False, "error_code": "payload_hash_mismatch"}),
        Response(403, {"accepted": False, "error_code": "resource_mismatch"}),
    ]

    def urlopen(call, timeout):
        calls.append(json.loads(call.data))
        return responses.pop(0)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    sink = PortalIngestionSink("https://portal.example", Tokens())
    request, config = values()
    receipt = sink.begin(request, config)
    sink.complete(receipt, {"metrics": [{"value": 1}]})
    replay = sink.replay_last_delivery()
    invalid = sink.prove_invalid_contract()
    mismatch = sink.prove_resource_mismatch()

    assert replay["outcome"] == "replayed"
    assert invalid == {"accepted": False, "error_code": "payload_hash_mismatch"}
    assert mismatch == {"accepted": False, "error_code": "resource_mismatch"}
    assert calls[0] == calls[1]
    assert calls[2]["run"]["importer_run_id"] != calls[0]["run"]["importer_run_id"]
    assert calls[2]["payload"]["metrics"][0]["value"] == 2
    assert calls[3]["resource"]["identity"] == "properties/999999999"
