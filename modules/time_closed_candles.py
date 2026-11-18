"""Opt-in, research-only time-closed candle projection.

A wall-clock close is NOT provider finality. This module never mutates provider
completion flags, authorizes trading, or changes the strict signal pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite

from modules.market_data_contracts import CandleBar, CandleSnapshot
from modules.market_session_gate import regular_session_bounds

STEP = timedelta(minutes=5)
DEFAULT_GRACE = timedelta(seconds=5)


def _utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class TimeClosedResearch:
    bars: tuple[CandleBar, ...]
    evidence: str
    reason: str
    actionable: bool = False
    opening_range: dict | None = None
    vwap: float | None = None
    ema9: float | None = None
    directional_context: str = "unknown"


def _valid(bar: CandleBar) -> bool:
    values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        return False
    return (bar.volume > 0 and bar.low > 0 and bar.high >= max(bar.open, bar.close, bar.low)
            and bar.low <= min(bar.open, bar.close) and bar.open > 0 and bar.close > 0)


def time_closed_research(
    initial: CandleSnapshot | None,
    refreshed: CandleSnapshot | None,
    *,
    now: datetime,
    enabled: bool = False,
    grace_seconds: int = 5,
) -> TimeClosedResearch:
    """Compare two independently retrieved snapshots; return provisional prefix.

    Caller MUST actually perform a new provider fetch after interval close.
    Equality is a consistency check, not proof that bars cannot be revised.
    """
    empty = lambda reason: TimeClosedResearch((), "time_closed_unverified_finality", reason)
    if not enabled:
        return empty("time_closed_mode_disabled")
    if not isinstance(grace_seconds, int) or isinstance(grace_seconds, bool) or not 0 <= grace_seconds <= 60:
        return empty("invalid_close_grace")
    if initial is None or refreshed is None:
        return empty("refetch_unavailable")
    now = _utc(now)
    bounds = regular_session_bounds(now)
    if bounds is None:
        return empty("no_authoritative_session")
    session_open, session_close = bounds
    if now < session_open:
        return empty("session_not_open")
    for snap in (initial, refreshed):
        if (snap.symbol not in ("SPY", "QQQ") or snap.interval != "5m" or snap.session != "regular"
            or snap.entitlement.get("allowed") is not True
            or snap.entitlement.get("provider") != snap.provider
            or snap.freshness not in ("fresh", "current")
            or snap.completeness == "incomplete"
            or "provider_incomplete_bars_skipped" in snap.warnings):
            return empty("invalid_snapshot_contract")
    if (initial.symbol, initial.provider) != (refreshed.symbol, refreshed.provider):
        return empty("refetch_source_mismatch")
    try:
        first_at, second_at = _utc(initial.retrieved_at), _utc(refreshed.retrieved_at)
    except (ValueError, TypeError, OverflowError):
        return empty("invalid_retrieval_time")
    if first_at > second_at or second_at > now or second_at < session_open:
        return empty("invalid_refetch_order")
    cutoff = min(now, second_at) - timedelta(seconds=grace_seconds)
    a = {}
    b = {}
    for snap, dest in ((initial, a), (refreshed, b)):
        last = None
        for bar in snap.candles:
            try:
                start = _utc(bar.time)
            except (ValueError, TypeError, OverflowError):
                return empty("invalid_bar_time")
            if last is not None and start <= last:
                return empty("out_of_order_or_duplicate_bars")
            last = start
            if not _valid(bar):
                return empty("invalid_ohlcv")
            if session_open <= start < session_close:
                if (start - session_open) % STEP != timedelta(0):
                    return empty("off_grid_bar")
                dest[start] = bar
    if not a or not b:
        return empty("session_prefix_missing")
    result = []
    start = session_open
    while start + STEP <= cutoff and start < session_close:
        left, right = a.get(start), b.get(start)
        if left is None or right is None:
            return empty("missing_or_unmatched_interval")
        if (left.open, left.high, left.low, left.close, left.volume) != (
            right.open, right.high, right.low, right.close, right.volume
        ):
            return empty("bar_revised_on_refetch")
        result.append(right)
        start += STEP
    if not result:
        return empty("no_elapsed_refetched_bars")
    # The latest accepted interval must have been retrieved after its close+grace.
    if second_at < _utc(result[-1].time) + STEP + timedelta(seconds=grace_seconds):
        return empty("refetch_before_close_grace")
    opening_range = None
    if len(result) >= 3:
        opening_range = {
            "high": max(b.high for b in result[:3]),
            "low": min(b.low for b in result[:3]),
            "bar_count": 3,
            "status": "provisional_time_closed",
        }
    volume = sum(b.volume for b in result)
    vwap = sum(((b.high + b.low + b.close) / 3) * b.volume for b in result) / volume
    ema9 = None
    if len(result) >= 9:
        ema9 = sum(b.close for b in result[:9]) / 9
        for bar in result[9:]:
            ema9 = bar.close * 0.2 + ema9 * 0.8
    context = "unknown"
    if ema9 is not None:
        if result[-1].close > vwap > ema9:
            context = "bullish"
        elif result[-1].close < vwap < ema9:
            context = "bearish"
        else:
            context = "neutral"
    return TimeClosedResearch(
        tuple(result), "closed_by_time", "provider_finality_not_attested",
        opening_range=opening_range, vwap=vwap, ema9=ema9,
        directional_context=context,
    )


def fetch_time_closed_research(
    fetch_snapshot,
    *,
    now: datetime,
    clock=None,
    enabled: bool = False,
    grace_seconds: int = 5,
) -> TimeClosedResearch:
    """Research-only caller for two independently fetched authorized snapshots.

    fetch_snapshot must retrieve a fresh, validated CandleSnapshot on each call.
    This function never changes the production trade-intelligence signal path.
    """
    if not enabled:
        return TimeClosedResearch((), "time_closed_unverified_finality", "time_closed_mode_disabled")
    try:
        first = fetch_snapshot()
        second = fetch_snapshot()
    except Exception:
        return TimeClosedResearch((), "time_closed_unverified_finality", "refetch_unavailable")
    return time_closed_research(
        first, second, now=clock() if clock is not None else now,
        enabled=True, grace_seconds=grace_seconds
    )
