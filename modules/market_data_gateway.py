"""Provider-independent market-data gateway over the existing Public adapter.

The gateway owns normalization, validation, timestamp/session classification,
freshness, completeness and snapshot identity. It does not create candles from
quotes, resample provider bars, fill gaps or infer permissions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from math import isfinite
from types import SimpleNamespace
from typing import Protocol

from modules.data_entitlements import (
    PRIVATE_RESEARCH,
    DataUseDenied,
    ProviderEntitlement,
    check_data_use,
    entitlement_for,
)
from modules.market_data_contracts import (
    AGGREGATION_BY_INTERVAL,
    INTERVAL_SECONDS,
    SUPPORTED_INTERVALS,
    SUPPORTED_SESSIONS,
    SUPPORTED_SYMBOLS,
    CandleBar,
    CandleBatch,
    CandleSnapshot,
    ProviderCapabilities,
    QuoteObservation,
)
from modules.market_session_gate import regular_session_bounds
from modules.public_intraday import PublicIntradayError, fetch_intraday_bars
from modules.public_provider import (
    PublicProviderError,
    _public_context,
    get_public_quotes,
    provider_error,
)
from modules.quote_freshness import freshness, market_state, normalize_timestamp

SNAPSHOT_SCHEMA_VERSION = "alphaos-candles-v1"
PUBLIC_CAPABILITIES = ProviderCapabilities(
    provider="Public",
    symbols=SUPPORTED_SYMBOLS,
    intervals=SUPPORTED_INTERVALS,
    sessions=SUPPORTED_SESSIONS,
    latest_quotes=True,
    native_candles=True,
    provider_native_intervals=True,
    expected_bar_metadata=True,
    entitlement=entitlement_for("Public").as_dict(),
)


class MarketDataError(RuntimeError):
    """A safe provider-independent market-data failure."""

    def __init__(self, code: str, status: int = 503, *, detail: dict | None = None):
        self.code = code
        self.status = status
        self.detail = detail
        super().__init__(code)


class MarketDataProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def quote(self, symbol: str) -> QuoteObservation: ...

    def candles(self, symbol: str, interval: str, session: str = "regular",
                limit: int = 390) -> CandleBatch: ...


def _clock(value=None) -> datetime:
    now = value or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Clock must be timezone-aware.")
    return now.astimezone(timezone.utc)


def _timestamp(value):
    normalized = normalize_timestamp(value)
    if normalized is None:
        raise MarketDataError("candle_timestamp_invalid")
    return datetime.fromisoformat(normalized)


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _validate_symbol(symbol: str) -> str:
    value = str(symbol).strip().upper()
    if value not in SUPPORTED_SYMBOLS:
        raise MarketDataError("unsupported_symbol", 400)
    return value


def _validate_request(interval: str, session: str, limit: int) -> None:
    if interval not in SUPPORTED_INTERVALS:
        raise MarketDataError("unsupported_interval", 400)
    if session not in SUPPORTED_SESSIONS:
        raise MarketDataError("unsupported_session", 400)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 390:
        raise MarketDataError("invalid_limit", 400)


def validate_candle_request(symbol: str, interval: str, session: str, limit: int) -> str:
    """Fail closed before any provider or cache access."""
    value = _validate_symbol(symbol)
    _validate_request(interval, session, limit)
    return value


def _session_relation(timestamp: datetime) -> tuple[str, datetime | None, datetime | None]:
    bounds = regular_session_bounds(timestamp)
    if bounds is None:
        return "non_session_day", None, None
    opening, closing = bounds
    if timestamp < opening:
        return "before_open", opening, closing
    if timestamp >= closing:
        return "after_close", opening, closing
    return "inside", opening, closing


def _regular_bar(timestamp: datetime) -> bool:
    return _session_relation(timestamp)[0] == "inside"


def _session_in_progress(latest: datetime, now: datetime) -> bool:
    """True only while the regular session containing the latest bar is open."""
    bounds = regular_session_bounds(latest)
    if bounds is None:
        return False
    opening, closing = bounds
    return opening <= now < closing


def _aligned(timestamp: datetime, interval: str) -> bool:
    step = INTERVAL_SECONDS[interval]
    return (timestamp.second == 0 and timestamp.microsecond == 0 and
            timestamp.minute % (step // 60) == 0)


def _validate_bars(symbol: str, interval: str, rows, *, now: datetime) -> tuple[tuple[CandleBar, ...], int | None, tuple[str, ...]]:
    bars: list[CandleBar] = []
    warnings: list[str] = []
    previous: datetime | None = None
    expected: int | None = None
    previous_session_date = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MarketDataError("candle_row_malformed")
        if str(row.get("symbol", "")).strip().upper() != symbol:
            raise MarketDataError("candle_symbol_mismatch")
        if row.get("aggregation") != AGGREGATION_BY_INTERVAL[interval]:
            raise MarketDataError("candle_aggregation_mismatch")
        stamp = _timestamp(row.get("timestamp"))
        if stamp > now:
            raise MarketDataError("candle_timestamp_future")
        relation, opening, closing = _session_relation(stamp)
        if relation != "inside":
            detail = {"bar_index": index, "bar_count": len(rows), "relation": relation}
            if relation == "before_open" and opening is not None:
                detail["minutes_before_open"] = int((opening - stamp).total_seconds() // 60)
            elif relation == "after_close" and closing is not None:
                detail["minutes_after_close"] = int((stamp - closing).total_seconds() // 60)
            raise MarketDataError("candle_outside_regular_session", detail=detail)
        if not _aligned(stamp, interval):
            raise MarketDataError("candle_interval_misaligned")
        if previous is not None and stamp <= previous:
            raise MarketDataError("duplicate_candle_timestamp" if stamp == previous else "candle_timestamp_out_of_order")
        raw_values = [row.get(key) for key in ("open", "high", "low", "close", "volume")]
        if any(value is None for value in raw_values):
            raise MarketDataError("candle_ohlc_missing")
        values = [_number(value) for value in raw_values]
        if any(value is None for value in values):
            raise MarketDataError("candle_ohlc_invalid")
        opening, high, low, close, volume = values
        if min(opening, high, low, close) <= 0 or volume < 0:
            raise MarketDataError("candle_ohlc_invalid")
        if high < max(opening, close) or low > min(opening, close) or high < low:
            raise MarketDataError("candle_ohlc_invalid")
        expected_count = _count(row.get("provider_expected_bars"))
        if expected_count is not None:
            if expected is not None and expected_count != expected:
                raise MarketDataError("candle_expected_bars_conflict")
            expected = expected_count
        # Detect an internal gap only within one session. The overnight break
        # between sessions is expected and must not be reported as missing bars.
        session_date = stamp.date()
        if previous is not None and session_date == previous_session_date:
            step = INTERVAL_SECONDS[interval]
            if (stamp - previous).total_seconds() > step:
                warnings.append("missing_bars")
        previous = stamp
        previous_session_date = session_date
        bars.append(CandleBar(stamp.isoformat(), opening, high, low, close, volume))
    if not bars:
        raise MarketDataError("no_candles")
    # Do not classify completeness here. The same count is normal while a
    # session is still open; build_snapshot owns that clock-aware decision.
    return tuple(bars), expected, tuple(dict.fromkeys(warnings))


def _candle_freshness(latest: datetime, interval: str, now: datetime) -> str:
    age = (now - latest).total_seconds()
    if age < -60:
        return "unknown"
    state, _ = market_state(now)
    max_age = max(INTERVAL_SECONDS[interval] * 2, 120)
    if state in ("regular_open", "extended_hours"):
        return "fresh" if age <= max_age else "stale"
    if state == "closed":
        bounds = regular_session_bounds(latest)
        if bounds is not None:
            _, closing = bounds
            if (closing - latest).total_seconds() <= max(INTERVAL_SECONDS[interval] * 3, 300):
                return "latest_available"
        return "stale"
    return "unknown"


def _last_bar_status(provider_status: bool | None) -> str:
    """Classify only from provider evidence, never from the local clock."""
    if provider_status is True:
        return "complete"
    if provider_status is False:
        return "partial"
    return "unknown"


def build_snapshot(batch: CandleBatch, *, now: datetime | None = None,
                   entitlement=None) -> CandleSnapshot:
    """Build a stable response snapshot from an already-normalized batch."""
    now = _clock(now)
    decision = entitlement or check_data_use(PRIVATE_RESEARCH, batch.provider)
    if not decision.allowed:
        raise DataUseDenied(decision)
    if not batch.bars:
        raise MarketDataError("no_candles")
    warnings = list(batch.warnings)
    latest = batch.bars[-1].time
    latest_dt = datetime.fromisoformat(latest)
    last_status = _last_bar_status(batch.last_bar_complete)
    if last_status == "unknown":
        warnings.append("last_bar_completion_unverified")
    # The clock can show that the current bar's interval is still open, but it
    # cannot prove provider completeness. Keep that signal as a warning.
    if latest_dt + timedelta(seconds=INTERVAL_SECONDS[batch.interval]) > now:
        warnings.append("last_bar_window_open")
    freshness_value = _candle_freshness(latest_dt, batch.interval, now)
    if freshness_value == "stale":
        warnings.append("stale_candles")
    elif freshness_value == "latest_available":
        warnings.append("latest_available_session")
    in_progress = _session_in_progress(latest_dt, now)
    if in_progress:
        warnings.append("session_in_progress")
    if batch.expected_bars is None:
        warnings.append("expected_bar_count_unavailable")
        completeness = "unknown"
    elif in_progress:
        # A full-session expected count is not a failure while the session is
        # still accumulating bars. The final count is not known yet.
        completeness = "unknown"
    elif (batch.received_bars < batch.expected_bars
          or "missing_bars" in warnings
          or "provider_incomplete_bars_skipped" in warnings):
        completeness = "incomplete"
        warnings.append("incomplete_session")
    else:
        completeness = "complete"
    canonical = {
        "provider": batch.provider,
        "symbol": batch.symbol,
        "interval": batch.interval,
        "session": batch.session,
        "retrieved_at": batch.retrieved_at,
        "expected_bars": batch.expected_bars,
        "received_bars": batch.received_bars,
        "bars": [bar.as_dict() for bar in batch.bars],
    }
    snapshot_id = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return CandleSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        symbol=batch.symbol,
        interval=batch.interval,
        provider=batch.provider,
        session=batch.session,
        retrieved_at=batch.retrieved_at,
        latest_candle_at=latest,
        snapshot_id=snapshot_id,
        expected_bars=batch.expected_bars,
        received_bars=batch.received_bars,
        returned_bars=len(batch.bars),
        completeness=completeness,
        last_bar_status=last_status,
        freshness=freshness_value,
        warnings=tuple(dict.fromkeys(warnings)),
        candles=batch.bars,
        provider_capabilities=batch.capabilities.as_dict(),
        entitlement=decision.as_dict(),
    )


class PublicMarketDataProvider:
    """Public implementation of the provider-neutral contract."""

    name = "Public"
    capabilities = PUBLIC_CAPABILITIES

    def __init__(self, *, context=None, clock=None):
        self._context = context or _public_context
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def quote(self, symbol: str) -> QuoteObservation:
        symbol = _validate_symbol(symbol)
        now = _clock(self.clock())
        try:
            rows = get_public_quotes((symbol,), _context=self._context)
        except Exception as exc:
            mapped = provider_error(exc)
            raise MarketDataError(mapped.code, 429 if mapped.code == "public_rate_limit" else 503) from None
        if not isinstance(rows, list):
            raise MarketDataError("invalid_provider_response")
        matches = [row for row in rows if isinstance(row, dict) and str(row.get("symbol", "")).upper() == symbol]
        if len(matches) != 1:
            raise MarketDataError("invalid_provider_response")
        raw = matches[0]
        last = _number(raw.get("last"))
        if last is None or last <= 0:
            raise MarketDataError("invalid_provider_response")
        retrieved = normalize_timestamp(raw.get("retrieved_at")) or now.isoformat()
        quality = freshness(raw, now, retrieved)
        state, _ = market_state(now)
        warnings = []
        if quality["data_status"] == "stale":
            warnings.append("stale_quote")
        elif quality["data_status"] == "unknown":
            warnings.append("quote_freshness_unknown")
        quote_session = quality.get("quote_session") or (
            "regular_session" if state == "regular_open" else quality.get("observation_context", "unknown"))
        return QuoteObservation(
            provider=self.name,
            symbol=symbol,
            last=last,
            bid=_number(raw.get("bid")),
            ask=_number(raw.get("ask")),
            previous_close=_number(raw.get("previous_close")),
            change=_number(raw.get("change")),
            change_pct=_number(raw.get("change_pct")),
            volume=_number(raw.get("volume")),
            quote_time=normalize_timestamp(raw.get("updated_at")),
            retrieved_at=retrieved,
            session=quote_session,
            market_state=state,
            freshness=quality["data_status"],
            freshness_reason=quality["freshness_reason"],
            warnings=tuple(warnings),
        )

    def candles(self, symbol: str, interval: str, session: str = "regular",
                limit: int = 390) -> CandleBatch:
        symbol = validate_candle_request(symbol, interval, session, limit)
        now = _clock(self.clock())
        try:
            client, _ = self._context()
            rows, diagnostics = fetch_intraday_bars(
                SimpleNamespace(client=client), symbol,
                AGGREGATION_BY_INTERVAL[interval], period="DAY", clock=self.clock,
                return_diagnostics=True,
            )
        except PublicProviderError as exc:
            raise MarketDataError(exc.code, 429 if exc.code == "public_rate_limit" else 503) from None
        except PublicIntradayError as exc:
            raise MarketDataError(exc.code, 503) from None
        except MarketDataError:
            raise
        except Exception:
            raise MarketDataError("invalid_provider_response") from None
        bars, expected, warnings = _validate_bars(symbol, interval, rows, now=now)
        total_received = len(bars)
        if limit < len(bars):
            bars = bars[-limit:]
        if expected is None:
            expected = _count(diagnostics.get("provider_expected_bars"))
        if diagnostics.get("provider_skipped_incomplete_bars"):
            warnings = warnings + ("provider_incomplete_bars_skipped",)
        return CandleBatch(
            provider=self.name,
            symbol=symbol,
            interval=interval,
            session=session,
            retrieved_at=now.isoformat(),
            bars=bars,
            expected_bars=expected,
            received_bars=total_received,
            last_bar_complete=None,
            warnings=tuple(dict.fromkeys(warnings)),
            capabilities=self.capabilities,
        )


def provider_entitlement(provider: str) -> ProviderEntitlement:
    return entitlement_for(provider)
