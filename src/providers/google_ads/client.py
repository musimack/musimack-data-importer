from __future__ import annotations

from typing import Any

from .config import GoogleAdsLocalConfig


class GoogleAdsClientDependencyError(RuntimeError):
    pass


class GoogleAdsReadOnlyQueryError(RuntimeError):
    pass


class GoogleAdsReadOnlyClient:
    """Thin read-only wrapper around the optional Google Ads SDK.

    The SDK is imported only when this class is instantiated by the explicit CLI path.
    """

    def __init__(self, config: GoogleAdsLocalConfig):
        try:
            from google.ads.googleads.client import GoogleAdsClient  # type: ignore
        except ImportError as exc:
            raise GoogleAdsClientDependencyError(
                "google-ads package is not installed; install it locally before running the live read-only exporter"
            ) from exc
        self._google_ads_exception_type = _google_ads_exception_type()
        self._client = GoogleAdsClient.load_from_dict(config.to_google_ads_sdk_dict())

    def run_gaql_query(self, customer_id: str, query: str) -> list[dict[str, Any]]:
        service = self._client.get_service("GoogleAdsService")
        try:
            stream = service.search_stream(customer_id=customer_id, query=query)
        except Exception as exc:
            raise self._safe_query_error(exc) from exc
        rows: list[dict[str, Any]] = []
        try:
            for batch in stream:
                for result in getattr(batch, "results", []):
                    rows.append(_row_to_dict(result))
        except Exception as exc:
            raise self._safe_query_error(exc) from exc
        return rows

    def _safe_query_error(self, exc: Exception) -> GoogleAdsReadOnlyQueryError:
        if self._google_ads_exception_type and isinstance(exc, self._google_ads_exception_type):
            return GoogleAdsReadOnlyQueryError(_format_google_ads_exception(exc))
        return GoogleAdsReadOnlyQueryError(type(exc).__name__)


def _google_ads_exception_type() -> type[Exception] | None:
    try:
        from google.ads.googleads.errors import GoogleAdsException  # type: ignore
    except ImportError:
        return None
    return GoogleAdsException


def _format_google_ads_exception(exc: Exception) -> str:
    parts = ["Google Ads API request failed"]
    request_id = getattr(exc, "request_id", None)
    if request_id:
        parts.append(f"request_id={request_id}")
    failure = getattr(exc, "failure", None)
    errors = getattr(failure, "errors", []) if failure is not None else []
    for error in errors:
        code = getattr(error, "error_code", None)
        message = getattr(error, "message", None)
        if code:
            parts.append(f"error_code={code}")
        if message:
            parts.append(f"message={message}")
    return "; ".join(parts)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    raw_pb = getattr(row, "_pb", None)
    if raw_pb is not None:
        try:
            from google.protobuf.json_format import MessageToDict

            return MessageToDict(raw_pb, preserving_proto_field_name=True)
        except Exception:
            pass
    return _object_to_dict(row)


def _object_to_dict(value: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name in dir(value):
        if name.startswith("_"):
            continue
        try:
            item = getattr(value, name)
        except Exception:
            continue
        if callable(item) or item is None:
            continue
        if isinstance(item, (str, int, float, bool)):
            output[name] = item
        elif isinstance(item, dict):
            output[name] = item
        elif hasattr(item, "__dict__") or hasattr(item, "_pb"):
            output[name] = _object_to_dict(item)
    return output
