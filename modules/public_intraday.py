"""Intraday Public OHLCV adapter.

Uses the Public SDK's historic-bars interface with DAY/ONE_MINUTE.
No resampling, forward-fill, or synthetic bars.

Failures carry a stable code and never include the provider payload, request
headers or credentials. Timestamp shape is classified only to explain a rejected
bar; the value itself is never logged.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from requests.exceptions import Timeout

from modules.quote_freshness import normalize_timestamp

SUPPORTED_AGGREGATIONS = {
    "ONE_MINUTE", "FIVE_MINUTES", "TEN_MINUTES", "FIFTEEN_MINUTES",
    "THIRTY_MINUTES", "ONE_HOUR",
}


class PublicIntradayError(RuntimeError):
    """A safe, stable Public intraday failure code."""

    def __init__(self, code: str, *, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code)


def _status_code(error: Exception) -> int | None:
    status = getattr(error, "status_code", None)
    if status is None:
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _fetch_error_code(error: Exception) -> str:
    status = _status_code(error)
    if status in (401, 403):
        return "provider_bars_authentication_failed"
    if status == 429:
        return "provider_bars_rate_limited"
    if isinstance(error, (Timeout, TimeoutError)):
        return "provider_bars_timeout"
    return "provider_bars_fetch_failed"


def _bar_value(bar, name):
    if isinstance(bar, dict):
        return bar.get(name)
    return getattr(bar, name, None)


def _timestamp_kind(value) -> str:
    """Classify shape without retaining or returning the timestamp value."""
    if value is None:
        return "missing"
    text = value if isinstance(value, str) else str(value)
    text = text.strip()
    if not text:
        return "missing"
    if re.fullmatch(r"\d{10,13}", text):
        return "epoch_string"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return "date_only"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "invalid"
    return "aware" if parsed.tzinfo is not None else "naive"


def _all_skipped_code(timestamp_failures: dict[str, int], *,
                      ohlc_missing: int, ohlc_invalid: int) -> str:
    for kind in ("missing", "naive", "epoch_string", "date_only", "invalid"):
        if timestamp_failures.get(kind):
            return f"provider_bars_timestamp_{kind}"
    if ohlc_missing:
        return "provider_bars_ohlc_missing"
    if ohlc_invalid:
        return "provider_bars_ohlc_invalid"
    return "provider_bars_empty"


def fetch_intraday_bars(provider, symbol, aggregation="ONE_MINUTE", *, period="DAY",
                        clock=None, return_diagnostics=False):
    if aggregation not in SUPPORTED_AGGREGATIONS:
        raise ValueError("Unsupported intraday aggregation.")
    if period not in {"DAY", "WEEK", "MONTH"}:
        raise ValueError("Unsupported intraday period.")

    try:
        from public_api_sdk import BarAggregation, BarPeriod
    except Exception:
        raise PublicIntradayError("provider_bars_sdk_unavailable") from None
    try:
        aggregation_value = getattr(BarAggregation, aggregation)
    except AttributeError:
        raise PublicIntradayError("provider_bars_aggregation_unsupported") from None
    try:
        period_value = getattr(BarPeriod, period)
    except AttributeError:
        raise PublicIntradayError("provider_bars_period_unsupported") from None
    try:
        response = provider.client.get_bars(
            symbol,
            period_value,
            aggregation=aggregation_value,
        )
    except Exception as error:
        raise PublicIntradayError(_fetch_error_code(error)) from None

    response_symbol = getattr(response, "symbol", None)
    if not isinstance(response_symbol, str) or response_symbol.strip().upper() != symbol:
        raise PublicIntradayError("provider_bars_symbol_mismatch")

    regular = getattr(response, "regular_market", None)
    if regular is None:
        raise PublicIntradayError("provider_bars_regular_market_missing")
    bars = getattr(regular, "bars", None)
    if bars is None:
        raise PublicIntradayError("provider_bars_list_missing")
    if not isinstance(bars, list):
        raise PublicIntradayError("provider_bars_list_malformed")
    if not bars:
        raise PublicIntradayError("provider_bars_empty")

    retrieved = (clock() if clock is not None else datetime.now(timezone.utc)).isoformat()
    expected = getattr(regular, "expected_bars", getattr(response, "total_expected_bars", None))
    if not (isinstance(expected, int) and not isinstance(expected, bool) and expected >= 0):
        expected = None
    received = len(bars)
    normalized = []
    skipped = 0
    timestamp_failures: dict[str, int] = {}
    ohlc_missing = 0
    ohlc_invalid = 0
    for bar in bars:
        raw_timestamp = _bar_value(bar, "timestamp")
        kind = _timestamp_kind(raw_timestamp)
        if kind != "aware":
            timestamp_failures[kind] = timestamp_failures.get(kind, 0) + 1
            skipped += 1
            continue
        timestamp = normalize_timestamp(raw_timestamp)
        if timestamp is None:
            timestamp_failures["invalid"] = timestamp_failures.get("invalid", 0) + 1
            skipped += 1
            continue

        raw_values = {
            "open": _bar_value(bar, "open"),
            "high": _bar_value(bar, "high"),
            "low": _bar_value(bar, "low"),
            "close": _bar_value(bar, "close"),
            "volume": _bar_value(bar, "volume"),
        }
        if any(value is None for value in raw_values.values()):
            ohlc_missing += 1
            skipped += 1
            continue
        try:
            values = {name: float(value) for name, value in raw_values.items()}
        except (TypeError, ValueError):
            ohlc_invalid += 1
            skipped += 1
            continue

        normalized.append({
            "schema_version": "intraday-bar-v1",
            "provider": "Public",
            "symbol": symbol,
            "aggregation": aggregation,
            "timestamp": timestamp,
            "open": values["open"],
            "high": values["high"],
            "low": values["low"],
            "close": values["close"],
            "volume": values["volume"],
            "retrieved_at": retrieved,
            "provider_period": period,
            "provider_expected_bars": expected,
            "provider_received_bars": received,
            "provider_skipped_incomplete_bars": skipped,
        })

    if not normalized:
        raise PublicIntradayError(_all_skipped_code(
            timestamp_failures, ohlc_missing=ohlc_missing, ohlc_invalid=ohlc_invalid))

    diagnostics = {
        "provider_period": period,
        "provider_expected_bars": expected,
        "provider_received_bars": received,
        "provider_skipped_incomplete_bars": skipped,
        "provider_timestamp_failures": dict(sorted(timestamp_failures.items())),
        "provider_ohlc_missing_bars": ohlc_missing,
        "provider_ohlc_invalid_bars": ohlc_invalid,
    }
    if return_diagnostics:
        return normalized, diagnostics
    return normalized
