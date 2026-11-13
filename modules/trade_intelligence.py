"""Verified SPY/QQQ trade intelligence over confirmed regular-session bars.

This is a projection over AlphaOS's existing market snapshot and candle
gateway. It does not fetch data, create a second research engine, infer missing
bars, or turn an underlying state into an options recommendation.

The final candle is excluded whenever provider completion is unverified. Earlier
bars are still usable because a later regular-session bar proves the provider
has moved past their interval. Opening-range, VWAP and EMA calculations fail
closed when the session grid is incomplete.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Iterable
from zoneinfo import ZoneInfo

from modules.market_data_contracts import CandleBar, CandleSnapshot
from modules.market_session_gate import regular_session_bounds

VERSION = "alphaos-trade-intelligence-v1"
BAR_STEP = timedelta(minutes=5)
OPENING_RANGE_BARS = 3
EMA_PERIOD = 9
NY = ZoneInfo("America/New_York")

_WARNING_MESSAGES = {
    "last_bar_completion_unverified": (
        "The provider did not confirm the newest candle. It was excluded from "
        "all calculations; only earlier bars were used."
    ),
    "last_bar_window_open": "The newest candle interval is still open and was excluded.",
    "stale_candles": "The intraday candle snapshot is stale for the current session.",
    "latest_available_session": "The snapshot is the latest completed regular session.",
    "session_in_progress": "The regular session is still accumulating bars.",
    "expected_bar_count_unavailable": "The provider did not publish an expected bar count.",
    "incomplete_session": "The provider reported an incomplete session.",
    "missing_bars": "The provider reported missing bars.",
    "provider_incomplete_bars_skipped": "The provider skipped incomplete bars.",
}


def _utc(value: str | datetime) -> datetime:
    instant = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if instant.tzinfo is None:
        raise ValueError("Timestamp must include a UTC offset.")
    return instant.astimezone(timezone.utc)


def _finite(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _price(value) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0 else None


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


@dataclass(frozen=True)
class ConfirmedSession:
    bars: tuple[CandleBar, ...]
    status: str
    reasons: tuple[str, ...]
    session_state: str
    session_date: str | None
    open_time: datetime | None
    close_time: datetime | None
    latest_confirmed_at: datetime | None
    opening_range: dict | None
    vwap: float | None
    ema9: float | None
    current_high: float | None
    current_low: float | None
    last_change: dict | None


def _ema9(closes: list[float]) -> float | None:
    if len(closes) < EMA_PERIOD:
        return None
    seed = sum(closes[:EMA_PERIOD]) / EMA_PERIOD
    alpha = 2 / (EMA_PERIOD + 1)
    for close in closes[EMA_PERIOD:]:
        seed = close * alpha + seed * (1 - alpha)
    return seed


def _empty_session(state: str, reason: str, *, session_date=None,
                   open_time=None, close_time=None) -> ConfirmedSession:
    return ConfirmedSession(
        bars=(), status="unavailable", reasons=(reason,), session_state=state,
        session_date=session_date, open_time=open_time, close_time=close_time,
        latest_confirmed_at=None, opening_range=None, vwap=None, ema9=None,
        current_high=None, current_low=None, last_change=None,
    )


def confirmed_session(
    snapshot: CandleSnapshot | None,
    *,
    now: datetime,
) -> ConfirmedSession:
    """Return only regular-session bars whose closes are supported by evidence."""
    now = _utc(now)
    bounds = regular_session_bounds(now)
    if bounds is None:
        return _empty_session("unknown", "no_authoritative_session")
    session_open, session_close = bounds
    session_date = session_open.astimezone(NY).date().isoformat()
    if now < session_open:
        return _empty_session(
            "preopen", "session_not_open",
            session_date=session_date, open_time=session_open, close_time=session_close,
        )
    state = "open" if now < session_close else "closed"
    if snapshot is None:
        return _empty_session(
            state, "no_candle_snapshot",
            session_date=session_date, open_time=session_open, close_time=session_close,
        )
    if snapshot.interval != "5m" or snapshot.session != "regular":
        return _empty_session(
            state, "unsupported_candle_contract",
            session_date=session_date, open_time=session_open, close_time=session_close,
        )
    if not snapshot.candles:
        return _empty_session(
            state, "no_candles",
            session_date=session_date, open_time=session_open, close_time=session_close,
        )

    try:
        retrieved = _utc(snapshot.retrieved_at)
        starts = [_utc(bar.time) for bar in snapshot.candles]
    except (TypeError, ValueError, OverflowError):
        return _empty_session(
            state, "invalid_candle_timestamps",
            session_date=session_date, open_time=session_open, close_time=session_close,
        )

    current = [
        bar for bar, start in zip(snapshot.candles, starts)
        if session_open <= start < session_close
    ]
    if not current:
        return _empty_session(
            state, "snapshot_not_current_session",
            session_date=session_date, open_time=session_open, close_time=session_close,
        )

    reasons = []
    raw_status = snapshot.last_bar_status
    # Only the final row can be a forming or unverified tail. If finality is
    # unknown, drop that row rather than treating a possibly changing close as
    # confirmed. A later bar proves earlier intervals have elapsed.
    if raw_status != "complete":
        reasons.append("last_bar_excluded_unconfirmed")
        current = current[:-1]
    elif _utc(current[-1].time) + BAR_STEP > min(now, retrieved) + timedelta(seconds=1):
        reasons.append("last_bar_window_open")
        current = current[:-1]
    if not current:
        return ConfirmedSession(
            bars=(), status="unavailable", reasons=tuple(_dedupe(reasons + ["no_confirmed_bars"])),
            session_state=state, session_date=session_date, open_time=session_open,
            close_time=session_close, latest_confirmed_at=None, opening_range=None,
            vwap=None, ema9=None, current_high=None, current_low=None, last_change=None,
        )

    # The snapshot must contain the opening bar. A chart beginning mid-session
    # cannot establish the opening range or a session VWAP.
    starts = [_utc(bar.time) for bar in current]
    if starts[0] != session_open:
        return ConfirmedSession(
            bars=tuple(current), status="incomplete",
            reasons=tuple(_dedupe(reasons + ["session_prefix_missing"])),
            session_state=state, session_date=session_date, open_time=session_open,
            close_time=session_close, latest_confirmed_at=starts[-1] + BAR_STEP,
            opening_range=None, vwap=None, ema9=None,
            current_high=max(bar.high for bar in current),
            current_low=min(bar.low for bar in current),
            last_change=_last_change(current),
        )
    gaps = [
        index for index, start in enumerate(starts)
        if start != session_open + index * BAR_STEP
    ]
    if gaps:
        reasons.append("session_grid_incomplete")
    for index, start in enumerate(starts):
        if start + BAR_STEP > min(now, retrieved) + timedelta(seconds=1):
            reasons.append("candle_not_closed")
            current = current[:index]
            starts = starts[:index]
            break
    if not current:
        return ConfirmedSession(
            bars=(), status="unavailable", reasons=tuple(_dedupe(reasons + ["no_confirmed_bars"])),
            session_state=state, session_date=session_date, open_time=session_open,
            close_time=session_close, latest_confirmed_at=None, opening_range=None,
            vwap=None, ema9=None, current_high=None, current_low=None, last_change=None,
        )

    contiguous = not gaps and len(current) == len(starts)
    opening_range = None
    if contiguous and len(current) >= OPENING_RANGE_BARS:
        opening = current[:OPENING_RANGE_BARS]
        opening_range = {
            "high": max(bar.high for bar in opening),
            "low": min(bar.low for bar in opening),
            "start": session_open.isoformat(),
            "end": (session_open + OPENING_RANGE_BARS * BAR_STEP).isoformat(),
            "bar_count": OPENING_RANGE_BARS,
            "status": "complete",
        }

    vwap = None
    if contiguous:
        volumes = [_finite(bar.volume) for bar in current]
        if all(volume is not None and volume > 0 for volume in volumes):
            total = sum(volumes)
            vwap = sum(
                ((bar.high + bar.low + bar.close) / 3) * volume
                for bar, volume in zip(current, volumes)
            ) / total
        else:
            reasons.append("vwap_volume_unavailable")

    ema9 = _ema9([bar.close for bar in current]) if contiguous else None
    if contiguous and ema9 is None:
        reasons.append("ema9_insufficient_confirmed_bars")

    status = "verified"
    if not contiguous:
        status = "incomplete"
    latest_confirmed = starts[-1] + BAR_STEP
    if state == "open":
        if snapshot.freshness == "stale":
            status = "stale"
            reasons.append("stale_candles")
        elif snapshot.freshness not in ("fresh", "unknown"):
            status = "stale"
            reasons.append("candle_freshness_not_live")
        elif now - latest_confirmed > timedelta(minutes=15):
            status = "stale"
            reasons.append("latest_confirmed_candle_too_old")
    elif snapshot.freshness == "stale":
        reasons.append("stale_candles")

    return ConfirmedSession(
        bars=tuple(current), status=status,
        reasons=tuple(_dedupe(reasons)),
        session_state=state, session_date=session_date,
        open_time=session_open, close_time=session_close,
        latest_confirmed_at=latest_confirmed, opening_range=opening_range,
        vwap=vwap, ema9=ema9,
        current_high=max(bar.high for bar in current),
        current_low=min(bar.low for bar in current),
        last_change=_last_change(current),
    )


def _last_change(bars: list[CandleBar]) -> dict | None:
    if len(bars) < 2:
        return None
    prior, latest = bars[-2], bars[-1]
    change = latest.close - prior.close
    return {
        "previous_at": prior.time,
        "current_at": latest.time,
        "previous_close": prior.close,
        "current_close": latest.close,
        "change": change,
        "change_pct": (change / prior.close * 100) if prior.close else None,
    }


def _previous_session(daily_bars: list[dict], session_date: str) -> dict:
    if not daily_bars:
        raise ValueError("Completed daily history is required.")
    row = daily_bars[-1]
    day = _day(row.get("date"))
    if day is None or day.isoformat() >= session_date:
        raise ValueError("The previous-session bar is not completed before the session.")
    open_price, high, low, close = (
        _price(row.get("open")), _price(row.get("high")),
        _price(row.get("low")), _price(row.get("close")),
    )
    if None in (open_price, high, low, close):
        raise ValueError("Previous-session OHLC must be positive and finite.")
    if high < max(open_price, close, low) or low > min(open_price, close, high):
        raise ValueError("Previous-session OHLC bounds are invalid.")
    return {
        "date": day.isoformat(),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _pivots(previous: dict) -> dict:
    high, low, close = previous["high"], previous["low"], previous["close"]
    pivot = (high + low + close) / 3
    return {
        "pivot": pivot,
        "r1": 2 * pivot - low,
        "s1": 2 * pivot - high,
        "r2": pivot + (high - low),
        "s2": pivot - (high - low),
    }


def _reference_levels(
    previous: dict,
    pivots: dict,
    session: ConfirmedSession,
    structure_levels: list[dict],
) -> list[dict]:
    levels = [
        {"id": "prior_high", "label": "Previous session high", "price": previous["high"], "kind": "resistance", "source": "previous_session_ohlc"},
        {"id": "prior_low", "label": "Previous session low", "price": previous["low"], "kind": "support", "source": "previous_session_ohlc"},
        {"id": "prior_close", "label": "Previous session close", "price": previous["close"], "kind": "mid", "source": "previous_session_ohlc"},
        {"id": "pivot", "label": "Pivot", "price": pivots["pivot"], "kind": "mid", "source": "previous_session_ohlc"},
        {"id": "r1", "label": "R1", "price": pivots["r1"], "kind": "resistance", "source": "previous_session_ohlc"},
        {"id": "r2", "label": "R2", "price": pivots["r2"], "kind": "resistance", "source": "previous_session_ohlc"},
        {"id": "s1", "label": "S1", "price": pivots["s1"], "kind": "support", "source": "previous_session_ohlc"},
        {"id": "s2", "label": "S2", "price": pivots["s2"], "kind": "support", "source": "previous_session_ohlc"},
    ]
    if session.opening_range:
        levels.extend([
            {"id": "or_high", "label": "Opening range high", "price": session.opening_range["high"], "kind": "resistance", "source": "confirmed_opening_range"},
            {"id": "or_low", "label": "Opening range low", "price": session.opening_range["low"], "kind": "support", "source": "confirmed_opening_range"},
        ])
    if session.vwap is not None:
        levels.append({"id": "vwap", "label": "Session VWAP", "price": session.vwap, "kind": "mid", "source": "confirmed_5m_bars"})
    if session.ema9 is not None:
        levels.append({"id": "ema9", "label": "EMA 9 (5m)", "price": session.ema9, "kind": "mid", "source": "confirmed_5m_bars"})
    for index, row in enumerate(structure_levels):
        price = _price(row.get("price") if row.get("price") is not None else row.get("level"))
        kind = row.get("kind") or row.get("side")
        if price is None or kind not in ("support", "resistance"):
            continue
        label = row.get("label") or row.get("source") or (
            f"{kind.title()} ({row.get('sources')})" if row.get("sources")
            else f"{kind.title()} reference"
        )
        levels.append({
            "id": f"structure_{index}",
            "label": str(label),
            "price": price,
            "kind": kind,
            "source": "existing_price_structure",
        })
    normalized = []
    for level in levels:
        price = _price(level.get("price"))
        if price is None:
            continue
        normalized.append({**level, "price": price})
    return normalized


def _nearest(levels: list[dict], kind: str, reference: float, *, above: bool) -> dict | None:
    candidates = [
        level for level in levels
        if level["kind"] == kind
        and (level["price"] > reference + 1e-9 if above else level["price"] < reference - 1e-9)
    ]
    return min(candidates, key=lambda level: abs(level["price"] - reference), default=None)


def _target(
    levels: list[dict], entry: float, direction: str, atr: float
) -> dict | None:
    candidates = [
        level for level in levels
        if level["id"] not in ("vwap", "ema9", "pivot")
        and (level["price"] > entry + max(atr * 0.15, 1e-6) if direction == "bullish"
             else level["price"] < entry - max(atr * 0.15, 1e-6))
    ]
    chosen = (
        min(candidates, key=lambda level: level["price"]) if direction == "bullish"
        else max(candidates, key=lambda level: level["price"])
    ) if candidates else None
    if chosen is not None:
        return {"price": chosen["price"], "basis": chosen["label"], "source": chosen["source"]}
    fallback = entry + max(atr * 1.5, entry * 0.002) if direction == "bullish" else entry - max(atr * 1.5, entry * 0.002)
    return {"price": fallback, "basis": "1.5 x ATR fallback", "source": "atr_reference"}


def _risk(entry: float | None, stop: float | None, target: dict | None) -> dict | None:
    if entry is None or stop is None:
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    target_price = _price(target.get("price")) if target else None
    distance = abs(target_price - entry) if target_price is not None else None
    return {
        "underlying_risk_distance": risk,
        "risk_pct": risk / entry * 100,
        "target_distance": distance,
        "reward_to_risk": (distance / risk) if distance is not None and risk > 0 else None,
    }


def _options(state: str) -> dict:
    if state == "BUY":
        families = ["long_call", "call_debit_spread"]
    elif state == "SELL":
        families = ["long_put", "put_debit_spread"]
    else:
        families = []
    return {
        "status": "not_evaluated",
        "strategy_families": families,
        "reason": (
            "No contract-level option chain or quote is part of this read-only "
            "contract. An underlying BUY/SELL state is not an options trade."
        ),
        "max_modeled_loss": None,
        "fits_small_account_budget": None,
    }


def _setup(
    *, setup_id: str, name: str, state: str, direction: str,
    evidence: list[str], missing: list[str],
    entry: dict | None, invalidation: dict | None,
    stop: dict | None, target: dict | None,
    timestamp: str | None, freshness: str, wait_reason: str | None,
) -> dict:
    entry_price = _price(entry.get("price")) if entry else None
    stop_price = _price(stop.get("price")) if stop else None
    return {
        "id": setup_id,
        "name": name,
        "state": state,
        "direction": direction,
        "evidence": evidence,
        "missing_conditions": missing,
        "entry_trigger": entry,
        "invalidation": invalidation,
        "stop_reference": stop,
        "target_reference": target,
        "risk": _risk(entry_price, stop_price, target),
        "options": _options(state),
        "timestamp": timestamp,
        "freshness": freshness,
        "wait_reason": wait_reason,
    }


def _data_wait(session: ConfirmedSession, setup_name: str, setup_id: str) -> dict | None:
    if session.status == "verified" and session.session_state == "open":
        return None
    if session.session_state == "closed":
        reason = "The regular session is closed; verified levels are shown but no new entry can trigger."
    elif session.session_state == "preopen":
        reason = "The regular session has not opened."
    elif session.status == "incomplete":
        reason = "The confirmed 5-minute session grid is incomplete, so this setup cannot be evaluated."
    elif session.status == "stale":
        reason = "Confirmed intraday evidence is stale for the current session."
    else:
        reason = "Confirmed intraday evidence is unavailable."
    return {
        "id": setup_id, "name": setup_name, "state": "WAIT", "direction": "unknown",
        "evidence": [], "missing_conditions": [reason],
        "entry_trigger": None, "invalidation": None, "stop_reference": None,
        "target_reference": None, "risk": None, "options": _options("WAIT"),
        "timestamp": session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
        "freshness": session.status,
        "wait_reason": reason,
    }


def _opening_range_setup(
    session: ConfirmedSession, levels: list[dict], atr: float,
) -> dict:
    name = "Opening-range breakout"
    blocked = _data_wait(session, name, "opening_range_breakout")
    if blocked:
        return blocked
    if session.opening_range is None:
        return _setup(
            setup_id="opening_range_breakout", name=name, state="WAIT", direction="unknown",
            evidence=[f"{len(session.bars)} confirmed five-minute bars are available."],
            missing=["Three complete opening five-minute bars (15 minutes)."],
            entry=None, invalidation=None, stop=None, target=None,
            timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="The 15-minute opening range is not complete.",
        )
    high, low = session.opening_range["high"], session.opening_range["low"]
    after = session.bars[OPENING_RANGE_BARS:]
    last = session.bars[-1]
    if not after:
        return _setup(
            setup_id="opening_range_breakout", name=name, state="WAIT", direction="unknown",
            evidence=[f"Opening range high {high:.2f}, low {low:.2f}."],
            missing=["A later confirmed five-minute close outside the range."],
            entry={"price": high, "condition": "Confirmed five-minute close above the opening-range high."},
            invalidation={"price": high, "condition": "Five-minute close back below the opening-range high."},
            stop={"price": low, "basis": "Opening-range low"},
            target=None, timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="The opening range is set; no later confirmed close is available yet.",
        )
    bull = [bar for bar in after if bar.close > high]
    bear = [bar for bar in after if bar.close < low]
    evidence = [f"Opening range high {high:.2f}, low {low:.2f}."]
    if bull and bear:
        return _setup(
            setup_id="opening_range_breakout", name=name, state="WAIT", direction="unknown",
            evidence=evidence + ["Confirmed closes occurred on both sides of the range."],
            missing=["A single directional close outside the range without an opposite-side close."],
            entry=None, invalidation=None, stop=None, target=None,
            timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="The opening range produced closes on both sides; this is chop, not a breakout.",
        )
    if not bull and not bear:
        return _setup(
            setup_id="opening_range_breakout", name=name, state="WAIT", direction="unknown",
            evidence=evidence + [f"Latest confirmed close {last.close:.2f} remains inside the range."],
            missing=["A confirmed five-minute close above the opening-range high or below the opening-range low."],
            entry={"price": high, "condition": "Confirmed five-minute close above the opening-range high."},
            invalidation={"price": high, "condition": "Five-minute close back below the opening-range high."},
            stop={"price": low, "basis": "Opening-range low"},
            target=None, timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="No confirmed five-minute close has left the opening range.",
        )

    above = bool(bull)
    first = bull[0] if above else bear[0]
    boundary = high if above else low
    opposite = low if above else high
    remains = last.close > high if above else last.close < low
    evidence.extend([
        f"First confirmed close {'above' if above else 'below'} the range: {first.close:.2f} at {first.time}.",
        f"Latest confirmed close {last.close:.2f} "
        f"{'remains above' if remains and above else 'remains below' if remains else 'has returned inside'} the range.",
    ])
    if not remains:
        return _setup(
            setup_id="opening_range_breakout", name=name, state="WAIT", direction="unknown",
            evidence=evidence,
            missing=["A new confirmed close outside the range after the failed breakout."],
            entry={"price": boundary, "condition": f"Confirmed five-minute close {'above' if above else 'below'} {boundary:.2f}."},
            invalidation={"price": boundary, "condition": "Five-minute close back inside the opening range."},
            stop={"price": opposite, "basis": "Opposite side of the opening range"},
            target=None, timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="False breakout: price closed back inside the opening range.",
        )

    direction = "bullish" if above else "bearish"
    stop_price = low if above else high
    target = _target(levels, boundary, direction, atr)
    return _setup(
        setup_id="opening_range_breakout", name=name,
        state="BUY" if above else "SELL", direction=direction,
        evidence=evidence, missing=[],
        entry={"price": boundary, "condition": (
            "Confirmed five-minute close above the opening-range high; a retest is optional."
            if above else "Confirmed five-minute close below the opening-range low; a retest is optional."
        )},
        invalidation={"price": boundary, "condition": (
            "Five-minute close back below the opening-range high."
            if above else "Five-minute close back above the opening-range low."
        )},
        stop={"price": stop_price, "basis": "Opposite side of the opening range"},
        target=target,
        timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
        freshness=session.status, wait_reason=None,
    )


def _vwap_setup(
    session: ConfirmedSession, levels: list[dict], atr: float,
) -> dict:
    name = "VWAP + EMA 9 continuation"
    blocked = _data_wait(session, name, "vwap_ema9_continuation")
    if blocked:
        return blocked
    if session.vwap is None or session.ema9 is None:
        missing = []
        if session.vwap is None:
            missing.append("Session VWAP requires positive volume on every confirmed bar.")
        if session.ema9 is None:
            missing.append("EMA 9 requires at least nine confirmed five-minute closes.")
        return _setup(
            setup_id="vwap_ema9_continuation", name=name, state="WAIT", direction="unknown",
            evidence=[f"{len(session.bars)} confirmed five-minute bars are available."],
            missing=missing, entry=None, invalidation=None, stop=None, target=None,
            timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="VWAP or EMA 9 is not available from the confirmed session bars.",
        )
    last = session.bars[-1]
    prior = session.bars[-2]
    vwap, ema9 = session.vwap, session.ema9
    bullish = last.close > vwap > ema9
    bearish = last.close < vwap < ema9
    evidence = [
        f"Latest confirmed close {last.close:.2f}.",
        f"Session VWAP {vwap:.2f}; EMA 9 {ema9:.2f}.",
    ]
    if not bullish and not bearish:
        return _setup(
            setup_id="vwap_ema9_continuation", name=name, state="WAIT", direction="unknown",
            evidence=evidence + ["Price, VWAP and EMA 9 are not in directional alignment."],
            missing=["Price above VWAP above EMA 9 for a bullish continuation, or the reverse for bearish."],
            entry=None, invalidation=None, stop=None, target=None,
            timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="The VWAP/EMA 9 alignment is mixed or contradictory.",
        )
    direction = "bullish" if bullish else "bearish"
    pullback_bars = session.bars[-4:]
    pullback = [
        bar for bar in pullback_bars
        if ((bar.low <= vwap and bar.close >= vwap) if bullish
            else (bar.high >= vwap and bar.close <= vwap))
    ]
    continuation = last.close > prior.close if bullish else last.close < prior.close
    evidence.append(
        "A pullback held VWAP." if pullback else "No pullback to VWAP occurred in the last four bars."
    )
    evidence.append(
        "The latest confirmed close continues in the aligned direction."
        if continuation else "The latest confirmed close did not continue in the aligned direction."
    )
    if not pullback or not continuation:
        missing = []
        if not pullback:
            missing.append("A pullback that tests VWAP and closes back on the trend side.")
        if not continuation:
            missing.append("A subsequent confirmed close continuing in the trend direction.")
        stop_price = (min(bar.low for bar in session.bars[-3:]) if bullish
                      else max(bar.high for bar in session.bars[-3:]))
        return _setup(
            setup_id="vwap_ema9_continuation", name=name, state="WAIT", direction=direction,
            evidence=evidence, missing=missing,
            entry={"price": last.close, "condition": "Confirmed close after a VWAP hold and continuation."},
            invalidation={"price": vwap, "condition": f"Five-minute close back {'below' if bullish else 'above'} VWAP."},
            stop={"price": stop_price, "basis": "Recent three-bar swing"},
            target=_target(levels, last.close, direction, atr),
            timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="Directional alignment exists, but the pullback/continuation sequence is incomplete.",
        )
    stop_price = (min(bar.low for bar in session.bars[-3:]) if bullish
                  else max(bar.high for bar in session.bars[-3:]))
    if (bullish and stop_price >= last.close) or (not bullish and stop_price <= last.close):
        stop_price = ema9
    return _setup(
        setup_id="vwap_ema9_continuation", name=name,
        state="BUY" if bullish else "SELL", direction=direction,
        evidence=evidence, missing=[],
        entry={"price": last.close, "condition": (
            "Confirmed close above VWAP after a VWAP hold and higher close."
            if bullish else "Confirmed close below VWAP after a VWAP rejection and lower close."
        )},
        invalidation={"price": vwap, "condition": f"Five-minute close back {'below' if bullish else 'above'} VWAP."},
        stop={"price": stop_price, "basis": "Recent three-bar swing / EMA 9 reference"},
        target=_target(levels, last.close, direction, atr),
        timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
        freshness=session.status, wait_reason=None,
    )


def _reversal_setup(
    session: ConfirmedSession, levels: list[dict], atr: float,
) -> dict:
    name = "Support/resistance reversal"
    blocked = _data_wait(session, name, "support_resistance_reversal")
    if blocked:
        return blocked
    last = session.bars[-1]
    support = _nearest(levels, "support", last.close, above=False)
    resistance = _nearest(levels, "resistance", last.close, above=True)
    window = session.bars[-4:]
    results = []
    if support:
        tests = [
            (index, bar) for index, bar in enumerate(window)
            if bar.low <= support["price"] * 1.001 and bar.close <= support["price"]
        ]
        if tests:
            test_index, test_bar = tests[-1]
            after = window[test_index + 1:]
            closes_above = [bar for bar in after if bar.close > support["price"]]
            evidence = [
                f"Verified support {support['label']} at {support['price']:.2f}.",
                f"Low {test_bar.low:.2f} tested support at {test_bar.time}.",
                f"{len(closes_above)} confirmed close(s) above support after the test.",
            ]
            if last.close < support["price"]:
                results.append((0, _setup(
                    setup_id="support_resistance_reversal", name=name, state="WAIT", direction="bullish",
                    evidence=evidence + ["The latest close is below support."],
                    missing=["A reclaim close above support."],
                    entry={"price": support["price"], "condition": "Confirmed close back above support."},
                    invalidation={"price": support["price"], "condition": "Five-minute close below support."},
                    stop={"price": test_bar.low, "basis": "Test-bar low below support"},
                    target=_target(levels, support["price"], "bullish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status,
                    wait_reason="Support was tested but the latest close did not reclaim it.",
                )))
            elif len(closes_above) < 2:
                results.append((1, _setup(
                    setup_id="support_resistance_reversal", name=name, state="WAIT", direction="bullish",
                    evidence=evidence,
                    missing=["A second confirmed close above support to avoid calling a single wick a reversal."],
                    entry={"price": support["price"], "condition": "Two consecutive confirmed closes above support after a test."},
                    invalidation={"price": support["price"], "condition": "Five-minute close below support."},
                    stop={"price": min(test_bar.low, support["price"]) - atr * 0.1, "basis": "Test low with ATR buffer"},
                    target=_target(levels, support["price"], "bullish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status,
                    wait_reason="Only one close has reclaimed support; follow-through is missing.",
                )))
            elif last.close > support["price"] and last.close > last.open:
                stop_price = min(test_bar.low, support["price"]) - atr * 0.1
                results.append((3, _setup(
                    setup_id="support_resistance_reversal", name=name, state="BUY", direction="bullish",
                    evidence=evidence + [f"Latest close {last.close:.2f} is above support with follow-through."],
                    missing=[],
                    entry={"price": last.close, "condition": "Confirmed reclaim and follow-through above verified support."},
                    invalidation={"price": support["price"], "condition": "Five-minute close below support."},
                    stop={"price": stop_price, "basis": "Test low with ATR buffer"},
                    target=_target(levels, last.close, "bullish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status, wait_reason=None,
                )))
            else:
                results.append((2, _setup(
                    setup_id="support_resistance_reversal", name=name, state="WAIT", direction="bullish",
                    evidence=evidence + ["Support was reclaimed, but the latest candle did not show bullish follow-through."],
                    missing=["A confirmed close above support that also closes above its open."],
                    entry={"price": support["price"], "condition": "Confirmed reclaim and bullish follow-through above support."},
                    invalidation={"price": support["price"], "condition": "Five-minute close below support."},
                    stop={"price": min(test_bar.low, support["price"]) - atr * 0.1, "basis": "Test low with ATR buffer"},
                    target=_target(levels, support["price"], "bullish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status,
                    wait_reason="Support was reclaimed but the latest candle lacks bullish follow-through.",
                )))
    if resistance:
        tests = [
            (index, bar) for index, bar in enumerate(window)
            if bar.high >= resistance["price"] * 0.999 and bar.close >= resistance["price"]
        ]
        if tests:
            test_index, test_bar = tests[-1]
            after = window[test_index + 1:]
            closes_below = [bar for bar in after if bar.close < resistance["price"]]
            evidence = [
                f"Verified resistance {resistance['label']} at {resistance['price']:.2f}.",
                f"High {test_bar.high:.2f} tested resistance at {test_bar.time}.",
                f"{len(closes_below)} confirmed close(s) below resistance after the test.",
            ]
            if last.close > resistance["price"]:
                results.append((0, _setup(
                    setup_id="support_resistance_reversal", name=name, state="WAIT", direction="bearish",
                    evidence=evidence + ["The latest close is above resistance."],
                    missing=["A rejection close below resistance."],
                    entry={"price": resistance["price"], "condition": "Confirmed close back below resistance."},
                    invalidation={"price": resistance["price"], "condition": "Five-minute close above resistance."},
                    stop={"price": test_bar.high, "basis": "Test-bar high above resistance"},
                    target=_target(levels, resistance["price"], "bearish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status,
                    wait_reason="Resistance was tested but the latest close did not reject it.",
                )))
            elif len(closes_below) < 2:
                results.append((1, _setup(
                    setup_id="support_resistance_reversal", name=name, state="WAIT", direction="bearish",
                    evidence=evidence,
                    missing=["A second confirmed close below resistance to avoid calling a single wick a reversal."],
                    entry={"price": resistance["price"], "condition": "Two consecutive confirmed closes below resistance after a test."},
                    invalidation={"price": resistance["price"], "condition": "Five-minute close above resistance."},
                    stop={"price": max(test_bar.high, resistance["price"]) + atr * 0.1, "basis": "Test high with ATR buffer"},
                    target=_target(levels, resistance["price"], "bearish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status,
                    wait_reason="Only one close has rejected resistance; follow-through is missing.",
                )))
            elif last.close < resistance["price"] and last.close < last.open:
                stop_price = max(test_bar.high, resistance["price"]) + atr * 0.1
                results.append((3, _setup(
                    setup_id="support_resistance_reversal", name=name, state="SELL", direction="bearish",
                    evidence=evidence + [f"Latest close {last.close:.2f} is below resistance with follow-through."],
                    missing=[],
                    entry={"price": last.close, "condition": "Confirmed rejection and follow-through below verified resistance."},
                    invalidation={"price": resistance["price"], "condition": "Five-minute close above resistance."},
                    stop={"price": stop_price, "basis": "Test high with ATR buffer"},
                    target=_target(levels, last.close, "bearish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status, wait_reason=None,
                )))
            else:
                results.append((2, _setup(
                    setup_id="support_resistance_reversal", name=name, state="WAIT", direction="bearish",
                    evidence=evidence + ["Resistance was rejected, but the latest candle did not show bearish follow-through."],
                    missing=["A confirmed close below resistance that also closes below its open."],
                    entry={"price": resistance["price"], "condition": "Confirmed rejection and bearish follow-through below resistance."},
                    invalidation={"price": resistance["price"], "condition": "Five-minute close above resistance."},
                    stop={"price": max(test_bar.high, resistance["price"]) + atr * 0.1, "basis": "Test high with ATR buffer"},
                    target=_target(levels, resistance["price"], "bearish", atr),
                    timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
                    freshness=session.status,
                    wait_reason="Resistance was rejected but the latest candle lacks bearish follow-through.",
                )))
    if not results:
        return _setup(
            setup_id="support_resistance_reversal", name=name, state="WAIT", direction="unknown",
            evidence=["No verified support or resistance level was tested in the last four confirmed bars."],
            missing=["A test of a verified level followed by a confirmed rejection or reclaim."],
            entry=None, invalidation=None, stop=None, target=None,
            timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="No verified level has a confirmed rejection or reclaim.",
        )
    confirmed = [entry for entry in results if entry[1]["state"] in ("BUY", "SELL")]
    if len({entry[1]["direction"] for entry in confirmed}) > 1:
        return _setup(
            setup_id="support_resistance_reversal", name=name, state="WAIT", direction="unknown",
            evidence=[entry[1]["evidence"][0] for entry in confirmed],
            missing=["One side of the range to fail before a directional reversal is confirmed."],
            entry=None, invalidation=None, stop=None, target=None,
            timestamp=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            freshness=session.status,
            wait_reason="Both support and resistance produced reversal evidence; the result is contradictory.",
        )
    return max(results, key=lambda entry: entry[0])[1]


def evaluate_option_candidate(
    *,
    strategy_family: str,
    max_modeled_loss: float | None,
    small_account_budget: float | None,
    quote_available: bool,
) -> dict:
    """Contract-level gate; an underlying setup never becomes a profitable trade."""
    if not quote_available:
        return {
            "status": "unavailable", "strategy_family": strategy_family,
            "max_modeled_loss": None, "fits_small_account_budget": None,
            "reason": "No executable contract-level quote was supplied.",
        }
    loss = _finite(max_modeled_loss)
    budget = _finite(small_account_budget)
    if loss is None or loss <= 0:
        return {
            "status": "unavailable", "strategy_family": strategy_family,
            "max_modeled_loss": None, "fits_small_account_budget": None,
            "reason": "Maximum modeled loss is unavailable for this exact structure.",
        }
    if budget is None or budget <= 0:
        return {
            "status": "unavailable", "strategy_family": strategy_family,
            "max_modeled_loss": loss, "fits_small_account_budget": None,
            "reason": "A positive small-account risk budget was not supplied.",
        }
    return {
        "status": "evaluated", "strategy_family": strategy_family,
        "max_modeled_loss": loss,
        "fits_small_account_budget": loss <= budget,
        "reason": "Contract-level risk gate only; no profitability or fill is asserted.",
    }


def evaluate_exit_early(
    *, position: dict | None, current_spot: float | None,
    confirmed_at: str | None, exit_quote_available: bool,
) -> dict:
    """EXIT EARLY exists only for an explicitly modeled position with verified evidence."""
    if not position:
        return {
            "state": "UNAVAILABLE",
            "reason": "No modeled position was supplied. Underlying setups do not create an exit state.",
        }
    required = ("direction", "invalidation", "max_modeled_loss")
    if any(position.get(key) is None for key in required):
        return {
            "state": "UNAVAILABLE",
            "reason": "The modeled position is missing its direction, invalidation, or maximum modeled loss.",
        }
    if not exit_quote_available:
        return {
            "state": "UNAVAILABLE",
            "reason": "No verified exit quote is available for the modeled position.",
        }
    spot = _price(current_spot)
    invalidation = _price(position.get("invalidation"))
    if spot is None or invalidation is None or confirmed_at is None:
        return {
            "state": "UNAVAILABLE",
            "reason": "Verified underlying or timestamp evidence is missing for the exit evaluation.",
        }
    direction = str(position["direction"]).lower()
    breached = spot <= invalidation if direction in ("bullish", "long", "call") else spot >= invalidation
    return {
        "state": "EXIT EARLY" if breached else "HOLD",
        "reason": (
            "The confirmed underlying price breached the modeled position invalidation."
            if breached else "The modeled position has not breached its verified invalidation."
        ),
        "confirmed_at": confirmed_at,
        "current_spot": spot,
        "invalidation": invalidation,
        "max_modeled_loss": position.get("max_modeled_loss"),
    }


def build_trade_intelligence(
    *,
    symbol: str,
    now: datetime,
    daily_bars: list[dict],
    intraday_snapshot: CandleSnapshot | None,
    atr: float,
    structure_levels: list[dict] | None = None,
    position: dict | None = None,
    exit_quote_available: bool = False,
) -> dict:
    """Build the versioned read-only trade-intelligence contract."""
    symbol = symbol.strip().upper()
    if symbol not in ("SPY", "QQQ"):
        raise ValueError("Only SPY and QQQ are supported.")
    now = _utc(now)
    atr = _price(atr)
    if atr is None:
        raise ValueError("A positive ATR is required.")
    session = confirmed_session(intraday_snapshot, now=now)
    session_date = session.session_date or now.astimezone(NY).date().isoformat()
    previous = _previous_session(daily_bars, session_date)
    pivots = _pivots(previous)
    levels = _reference_levels(previous, pivots, session, structure_levels or [])
    setups = [
        _opening_range_setup(session, levels, atr),
        _vwap_setup(session, levels, atr),
        _reversal_setup(session, levels, atr),
    ]

    confirmed = [setup for setup in setups if setup["state"] in ("BUY", "SELL")]
    directions = {setup["direction"] for setup in confirmed}
    if len(directions) == 1:
        overall_state = "BUY" if directions == {"bullish"} else "SELL"
        overall_reason = (
            f"{len(confirmed)} confirmed setup(s) align with a {next(iter(directions))} underlying state."
        )
    elif len(directions) > 1:
        overall_state = "WAIT"
        overall_reason = "Confirmed setups disagree on direction; no single research state is asserted."
    else:
        overall_state = "WAIT"
        closest = min(setups, key=lambda setup: len(setup["missing_conditions"]))
        overall_reason = closest["wait_reason"] or "No setup has met its confirmed entry conditions."

    if confirmed:
        active = confirmed[0]
    else:
        active = min(setups, key=lambda setup: (len(setup["missing_conditions"]), setups.index(setup)))
    last = session.bars[-1] if session.bars else None
    descriptive_bias = "unknown"
    if last is not None and session.vwap is not None and session.ema9 is not None:
        if last.close > session.vwap > session.ema9:
            descriptive_bias = "bullish"
        elif last.close < session.vwap < session.ema9:
            descriptive_bias = "bearish"
        else:
            descriptive_bias = "neutral"

    warnings = []
    for code in (intraday_snapshot.warnings if intraday_snapshot else ()):
        message = _WARNING_MESSAGES.get(code, code.replace("_", " "))
        warnings.append(message)
    if "last_bar_excluded_unconfirmed" in session.reasons:
        warnings.append(_WARNING_MESSAGES["last_bar_completion_unverified"])
    if "session_grid_incomplete" in session.reasons:
        warnings.append("Confirmed bars are missing from the regular-session grid; intraday setups are not evaluated.")
    if "session_prefix_missing" in session.reasons:
        warnings.append("The snapshot does not begin at the regular-session open.")
    if session.status == "stale":
        warnings.append("Intraday evidence is stale; no live setup is asserted.")
    if session.session_state == "closed":
        warnings.append("The regular session is closed; levels are the last verified session values.")
    try:
        gap = (date.fromisoformat(session_date) - date.fromisoformat(previous["date"])).days
        if gap > 4:
            warnings.append("The last completed daily bar is more than four calendar days before the session; review exchange holidays and data gaps.")
    except ValueError:
        pass

    return {
        "schema_version": VERSION,
        "symbol": symbol,
        "generated_at": now.isoformat(),
        "source": intraday_snapshot.provider if intraday_snapshot else None,
        "session": {
            "state": session.session_state,
            "date": session.session_date,
            "open": session.open_time.isoformat() if session.open_time else None,
            "close": session.close_time.isoformat() if session.close_time else None,
            "as_of": now.isoformat(),
        },
        "data": {
            "status": session.status,
            "provider": intraday_snapshot.provider if intraday_snapshot else None,
            "snapshot_id": intraday_snapshot.snapshot_id if intraday_snapshot else None,
            "retrieved_at": intraday_snapshot.retrieved_at if intraday_snapshot else None,
            "latest_candle_at": intraday_snapshot.latest_candle_at if intraday_snapshot else None,
            "latest_confirmed_candle_at": session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            "freshness": intraday_snapshot.freshness if intraday_snapshot else "unavailable",
            "completeness": intraday_snapshot.completeness if intraday_snapshot else "unavailable",
            "last_bar_status": intraday_snapshot.last_bar_status if intraday_snapshot else "unknown",
            "returned_bars": intraday_snapshot.returned_bars if intraday_snapshot else 0,
            "confirmed_bars": len(session.bars),
            "warnings": list(intraday_snapshot.warnings) if intraday_snapshot else [],
            "reasons": list(session.reasons),
        },
        "levels": {
            "previous_session": previous,
            "current_session": {
                "high": session.current_high,
                "low": session.current_low,
            },
            "pivots": pivots,
            "opening_range": session.opening_range or {
                "high": None, "low": None, "start": None, "end": None,
                "bar_count": 0, "status": "unavailable",
            },
            "vwap": {
                "price": session.vwap,
                "status": "available" if session.vwap is not None else "unavailable",
                "basis": "Typical price weighted by confirmed regular-session volume.",
            },
            "ema9": {
                "price": session.ema9,
                "status": "available" if session.ema9 is not None else "unavailable",
                "basis": "EMA 9 over confirmed five-minute closes; seeded with the first nine closes.",
            },
            "references": levels,
        },
        "bias": {
            "direction": descriptive_bias,
            "basis": "Descriptive alignment of the latest confirmed close, session VWAP and EMA 9.",
        },
        "state": overall_state,
        "reason": overall_reason,
        "active_setup_id": active["id"] if confirmed else None,
        "closest_setup_id": active["id"],
        "setups": setups,
        "last_change": session.last_change,
        "exit_early": evaluate_exit_early(
            position=position, current_spot=last.close if last else None,
            confirmed_at=session.latest_confirmed_at.isoformat() if session.latest_confirmed_at else None,
            exit_quote_available=exit_quote_available,
        ),
        "warnings": list(dict.fromkeys(warnings)),
        "disclaimer": (
            "BUY and SELL describe confirmed underlying research states, not orders or "
            "options recommendations. No probability, confidence score, fill, or profit is asserted."
        ),
    }
