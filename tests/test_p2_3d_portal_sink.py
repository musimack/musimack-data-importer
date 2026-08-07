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
