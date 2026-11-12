"""Internal SPY/QQQ opening-range evidence, independent of options eligibility."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from modules.data_entitlements import PRIVATE_RESEARCH, check_data_use
from modules.market_data_contracts import CandleSnapshot, SUPPORTED_SYMBOLS
from modules.market_session_gate import regular_session_bounds

_STEP = timedelta(minutes=5)
_OPENING_BARS = 3


@dataclass(frozen=True)
class EntryConfirmation:
    decision: Literal["BUY", "SELL", "WAIT"]
    data_status: Literal["fresh", "delayed", "stale", "unavailable"]
    reason: str
    explanation: str
    symbol: str | None = None
    snapshot_id: str | None = None
    opening_high: float | None = None
    opening_low: float | None = None
    confirmed_at: datetime | None = None


def _utc(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.utcoffset() is None:
        raise ValueError("Timestamp must have a UTC offset.")
    return instant.astimezone(timezone.utc)


def confirm_opening_range(
    snapshot: CandleSnapshot | None, *, as_of: datetime
) -> EntryConfirmation:
    """Evaluate the newest elapsed 5m bar of a private gateway snapshot.

    Only accept a server-created snapshot. Its bars are already normalized by
    the gateway; only the final row can be a forming or unverified tail.
    A signal describes the underlying's first close outside today's 15-minute
    range. It confers no option eligibility, pricing, or authority to trade.
    """
    if as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware.")
    now = as_of.astimezone(timezone.utc)
    if snapshot is None:
        return EntryConfirmation("WAIT", "unavailable", "no_snapshot", "No candle snapshot is available.")

    def wait(status, reason, explanation):
        return EntryConfirmation("WAIT", status, reason, explanation, snapshot.symbol, snapshot.snapshot_id)

    if (
        snapshot.symbol not in SUPPORTED_SYMBOLS
        or snapshot.interval != "5m"
        or snapshot.session != "regular"
    ):
        return wait("unavailable", "unsupported_snapshot", "Use SPY or QQQ five-minute regular-session candles.")
    if not (
        snapshot.entitlement.get("allowed") is True
        and snapshot.entitlement.get("use_context") == PRIVATE_RESEARCH
        and snapshot.entitlement.get("provider") == snapshot.provider
        and check_data_use(PRIVATE_RESEARCH, snapshot.provider).allowed
    ):
        return wait("unavailable", "research_use_denied", "This snapshot is unavailable for private research.")

    bounds = regular_session_bounds(now)
    if bounds is None or not bounds[0] <= now < bounds[1]:
        return wait("unavailable", "session_closed", "The NYSE regular session is closed.")
    opening, _ = bounds
    if not snapshot.candles:
        return wait("unavailable", "no_candles", "The snapshot contains no candles.")
    try:
        retrieved = _utc(snapshot.retrieved_at)
        starts = tuple(_utc(bar.time) for bar in snapshot.candles)
        latest = _utc(snapshot.latest_candle_at)
    except (TypeError, ValueError, OverflowError):
        return wait("unavailable", "invalid_timestamps", "The candle timestamps could not be verified.")
    if retrieved > now or latest != starts[-1] or any(start > retrieved for start in starts):
        return wait("unavailable", "invalid_timestamps", "The snapshot is inconsistent with the decision time.")

    if latest < opening or snapshot.freshness in {"stale", "latest_available"}:
        return wait("stale", "stale_snapshot", "The candles are stale for the current session.")
    if snapshot.freshness == "delayed":
        return wait("delayed", "delayed_snapshot", "The candle feed is delayed.")
    if snapshot.freshness != "fresh":
        return wait("unavailable", "unknown_freshness", "Candle freshness could not be verified.")
    if snapshot.last_bar_status != "complete" or latest + _STEP > retrieved:
        return wait("unavailable", "unconfirmed_close", "The provider has not confirmed the latest elapsed candle close.")

    # A chart can omit its opening rows or an entire interior bar even when
    # the vendor's expected count is unknown. Verify the regular-session grid.
    for i, start in enumerate(starts):
        if start != opening + i * _STEP:
            return wait("unavailable", "incomplete_session_prefix", "Candles are missing or out of order since the opening bell.")
    if now >= latest + 2 * _STEP:
        return wait("delayed", "latest_close_missing", "A newer candle has elapsed and its close is missing.")
    if len(starts) < _OPENING_BARS:
        return wait("fresh", "range_forming", "The first 15 minutes have not closed yet.")
    if len(starts) == _OPENING_BARS:
        return wait("fresh", "waiting_for_break", "The opening range is set. Waiting for a later close outside it.")

    opening_bars = snapshot.candles[:_OPENING_BARS]
    high = max(bar.high for bar in opening_bars)
    low = min(bar.low for bar in opening_bars)
    close = snapshot.candles[-1].close
    if low <= close <= high:
        return wait("fresh", "inside_range", "The latest candle closed inside or on the opening range.")
    if any(not low <= bar.close <= high for bar in snapshot.candles[_OPENING_BARS:-1]):
        return wait("fresh", "break_already_seen", "An earlier candle already closed outside the opening range.")

    above = close > high
    return EntryConfirmation(
        "BUY" if above else "SELL", "fresh", "opening_range_break",
        "The underlying closed above the opening range." if above
        else "The underlying closed below the opening range.",
        snapshot.symbol, snapshot.snapshot_id, high, low, latest + _STEP,
    )
