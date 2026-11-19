"""Point-in-time rules for the SPY/QQQ underlying-price playbook."""
from __future__ import annotations

from datetime import datetime, timedelta
from dataclasses import dataclass
from math import isfinite
from statistics import median

from modules.market_data_contracts import CandleSnapshot
from modules.research_calendar import nyse_schedule
from modules.trade_intelligence import OPENING_RANGE_BARS

BAR = timedelta(minutes=5)
MAX_AGE = 2 * BAR
VERSION = "market-playbook-v1"


@dataclass(frozen=True)
class PriorSession:
    symbol: str
    session: str
    provider: str
    observed_at: str
    high: float
    low: float
    close: float


def stamp(value):
    return datetime.fromisoformat(value)


def next_interval(value):
    aligned = value.replace(minute=value.minute // 5 * 5, second=0, microsecond=0)
    return aligned if value == aligned else aligned + BAR


def price_label(value):
    text = str(value)
    whole, _, decimals = text.partition(".")
    return f"{whole}.{decimals.ljust(2, '0')}"


def session_windows(now):
    schedule = nyse_schedule(now.date() - timedelta(days=14), now.date())
    return [
        (row.market_open.to_pydatetime(), row.market_close.to_pydatetime())
        for row in schedule.itertuples() if row.market_open <= now
    ][-2:]


def contiguous(rows, start, end):
    return len(rows) == (end - start) // BAR and all(
        stamp(row.time) == start + index * BAR for index, row in enumerate(rows)
    )


def pivots(rows):
    for index in range(2, len(rows) - 2):
        window = rows[index - 2:index + 3]
        if not contiguous(window, stamp(window[0].time), stamp(window[-1].time) + BAR):
            continue
        if any(bar.provider_complete is not True for bar in window):
            continue
        middle = rows[index]
        others = window[:2] + window[3:]
        if middle.high > max(bar.high for bar in others):
            yield middle, middle.high, "swing high"
        if middle.low < min(bar.low for bar in others):
            yield middle, middle.low, "swing low"


def ranked_levels(rows, previous, opening, prior_window, provenance, daily=None):
    evidence = []

    def add(bar, price, kind, available, source="native five-minute candle"):
        evidence.append({
            "price": price, "kind": kind, "observed_at": bar if isinstance(bar, str) else bar.time,
            "source": source,
            "confirmation_window_end": available.isoformat(),
            "available_at": provenance.get("retrieved_at", available.isoformat())
            if source == "native five-minute candle" else available.isoformat(),
        })

    if prior_window and previous and contiguous(previous, *prior_window) and all(
        bar.provider_complete is True for bar in previous
    ):
        high = max(previous, key=lambda bar: bar.high)
        low = min(previous, key=lambda bar: bar.low)
        add(high, high.high, "previous session high", prior_window[1])
        add(low, low.low, "previous session low", prior_window[1])
        add(previous[-1], previous[-1].close, "previous session close", prior_window[1])
    elif daily:
        for field in ("high", "low", "close"):
            add(prior_window[1].isoformat(), getattr(daily, field),
                f"previous session {field}", stamp(daily.observed_at), "completed daily OHLC")
    first = rows[:OPENING_RANGE_BARS]
    range_end = opening + OPENING_RANGE_BARS * BAR
    if contiguous(first, opening, range_end) and all(bar.provider_complete is True for bar in first):
        high = max(first, key=lambda bar: bar.high)
        low = min(first, key=lambda bar: bar.low)
        add(high, high.high, "opening range high", range_end)
        add(low, low.low, "opening range low", range_end)
    reactions = list(pivots(rows))
    for bar, price, kind in reactions:
        add(bar, price, kind, stamp(bar.time) + 3 * BAR)
    if not evidence:
        return []

    confirmed = [bar for bar in rows if bar.provider_complete is True]
    ranges = [bar.high - bar.low for bar in (confirmed or previous)[-14:]]
    tolerance = max(.01, .20 * median(ranges)) if ranges else .01
    groups = []
    for item in sorted(evidence, key=lambda proof: proof["price"]):
        if not groups or item["price"] - groups[-1][0]["price"] > tolerance:
            groups.append([])
        groups[-1].append(item)

    levels = []
    for group in groups:
        low, high = group[0]["price"], group[-1]["price"]
        times = sorted({item["observed_at"] for item in group})
        kinds = sorted({item["kind"] for item in group})
        swing_highs = [item for item in group if item["kind"] == "swing high"]
        swing_lows = [item for item in group if item["kind"] == "swing low"]
        flips = []
        for origin, retests, direction in (
            (swing_highs, swing_lows, "resistance to support"),
            (swing_lows, swing_highs, "support to resistance"),
        ):
            for retest in retests:
                if any(
                    stamp(source["confirmation_window_end"]) <= stamp(bar.time) < stamp(retest["observed_at"])
                    and bar.provider_complete is True
                    and (bar.close > high if direction == "resistance to support" else bar.close < low)
                    for source in origin for bar in rows
                ):
                    flips.append(direction)
                    break
        structural = max(3 if kind.startswith("previous session") else
                         2 if kind.startswith("opening range") else 1 for kind in kinds)
        levels.append({
            "low": low, "high": high, "types": kinds + flips, "evidence": group,
            "reactions": len({item["observed_at"] for item in swing_highs + swing_lows}),
            "observations": len(times), "last_observed_at": times[-1],
            "structural_weight": structural, "provenance": provenance,
        })
    levels.sort(key=lambda level: (
        level["observations"], level["reactions"], level["structural_weight"], level["last_observed_at"],
        -level["low"],
    ), reverse=True)
    for rank, level in enumerate(levels, 1):
        level["rank"] = rank
    return levels


def evaluate(snapshot: CandleSnapshot, now, daily: PriorSession | None = None):
    """Return current evidence, immutable proposals and lifecycle-eligible bars."""
    windows = session_windows(now)
    result = {
        "version": VERSION, "symbol": snapshot.symbol, "session": None,
        "as_of": snapshot.retrieved_at, "provider": snapshot.provider,
        "levels": [], "vwap": None, "provisional_range": None, "bias": "Undetermined",
        "structure": "No verified intraday structure.",
        "quality": "Insufficient", "status": "INSUFFICIENT DATA",
        "reason": "Regular-session evidence is unavailable.", "coverage": {},
    }
    if not windows or stamp(snapshot.retrieved_at) > now or snapshot.interval != "5m":
        return result, [], []
    opening, closing = windows[-1]
    session = opening.date().isoformat()
    prior = windows[-2] if len(windows) == 2 else None
    available = stamp(snapshot.retrieved_at)
    closed_rows = [bar for bar in snapshot.candles if stamp(bar.time) + BAR <= available]
    rows = [bar for bar in closed_rows if opening <= stamp(bar.time) < closing]
    previous = [bar for bar in closed_rows if prior and prior[0] <= stamp(bar.time) < prior[1]]
    confirmed = [bar for bar in rows if bar.provider_complete is True]
    current = opening <= now < closing
    fresh = bool(
        confirmed and now - available <= MAX_AGE
        and now - stamp(confirmed[-1].time) <= MAX_AGE
        and snapshot.freshness in (("fresh",) if current else ("fresh", "latest_available"))
        and not any("delay" in warning.lower() for warning in snapshot.warnings)
    )
    provenance = {"provider": snapshot.provider, "snapshot_id": snapshot.snapshot_id,
                  "retrieved_at": snapshot.retrieved_at,
                  "freshness": "fresh" if current and fresh else "historical" if not current else "stale_or_unconfirmed"}
    if daily and not (
        prior and daily.session == prior[0].date().isoformat()
        and daily.provider == snapshot.provider and daily.symbol == snapshot.symbol
        and prior[1] <= stamp(daily.observed_at) <= now
        and all(isfinite(price) and price > 0 for price in (daily.high, daily.low, daily.close))
        and daily.low <= daily.close <= daily.high
    ):
        daily = None
    levels = ranked_levels(rows, previous, opening, prior, provenance, daily)
    first = rows[:OPENING_RANGE_BARS]
    provisional_range = None
    if contiguous(first, opening, opening + OPENING_RANGE_BARS * BAR) and any(
        bar.provider_complete is not True for bar in first
    ):
        provisional_range = {"low": min(bar.low for bar in first),
                             "high": max(bar.high for bar in first)}
    expected = (min(available, closing) - opening) // BAR
    prefix_end = opening + max(0, expected) * BAR
    complete = bool(rows and contiguous(rows, opening, prefix_end) and len(rows) == len(confirmed))
    volume = sum(bar.volume for bar in rows)
    vwap = None
    if volume > 0 and all(bar.volume > 0 for bar in rows) and contiguous(rows, opening, prefix_end):
        vwap = {
            "value": sum((bar.high + bar.low + bar.close) * bar.volume / 3 for bar in rows) / volume,
            "as_of": (stamp(rows[-1].time) + BAR).isoformat(),
            "status": "confirmed" if complete else "provisional",
        }
    result.update(session=session, levels=levels, vwap=vwap, provisional_range=provisional_range,
                  coverage={"expected_closed": max(0, expected), "received_closed": len(rows),
                            "provider_confirmed": len(confirmed)}, provenance=provenance)
    if not current:
        result["reason"] = "The regular session is closed. Current triggers require an open session."
    elif not confirmed:
        result["reason"] = "Waiting for provider-confirmed five-minute candles. Time-closed candles alone cannot confirm a trigger."
    elif not fresh:
        result["reason"] = "Provider-confirmed five-minute evidence is stale or delayed."
    elif not complete:
        result["reason"] = "Waiting for a contiguous, provider-confirmed five-minute series from the regular open."
    else:
        result.update(status="WAIT", quality="Mixed")
        spot = confirmed[-1].close
        result["structure"] = f"Last confirmed five-minute close {spot:.2f}. No verified VWAP alignment."
        if vwap and len(confirmed) >= 3:
            higher = confirmed[-1].close > confirmed[-3].close
            lower = confirmed[-1].close < confirmed[-3].close
            momentum = "above" if higher else "below" if lower else "at"
            position = "above" if spot > vwap["value"] else "below" if spot < vwap["value"] else "at"
            result["structure"] = f"Last confirmed close {spot:.2f} is {momentum} its level two bars ago and {position} VWAP."
            if higher and spot > vwap["value"]:
                result["bias"] = "Bullish"
            elif lower and spot < vwap["value"]:
                result["bias"] = "Bearish"
            else:
                result["bias"] = "Mixed"
        below = sorted((level for level in levels if level["high"] < spot),
                       key=lambda level: level["high"], reverse=True)
        above = sorted((level for level in levels if level["low"] > spot),
                       key=lambda level: level["low"])
        proposals = []
        if next_interval(now) >= closing:
            result["reason"] = "No full five-minute interval remains for a new thesis."
            return result, proposals, confirmed
        for direction, candidates, opposing in (
            ("bullish", above, below), ("bearish", below, above),
        ):
            if len(candidates) < 2:
                continue
            zone, objective = candidates[:2]
            bullish = direction == "bullish"
            trigger = zone["high"] if bullish else zone["low"]
            invalidation = zone["low"] if bullish else zone["high"]
            target = objective["low"] if bullish else objective["high"]
            comparator = "above" if bullish else "below"
            reverse = "below" if bullish else "above"
            opposing_bias = result["bias"] not in ("Undetermined", direction.title())
            family = "breakout" if bullish else "breakdown"
            proposals.append({
                "id": f"{VERSION}/{snapshot.provider}/{snapshot.symbol}/{session}/{family}",
                "symbol": snapshot.symbol, "session": session, "direction": direction,
                "family": family, "created_at": now.isoformat(), "expires_at": closing.isoformat(),
                "trigger": trigger, "invalidation": invalidation, "target": target,
                "confirmation": f"A provider-confirmed five-minute candle closes {comparator} {price_label(trigger)}.",
                "invalidation_condition": f"After confirmation, a five-minute candle closes {reverse} {price_label(invalidation)}.",
                "target_condition": f"After confirmation, a five-minute candle closes at or beyond {price_label(target)}.",
                "thesis": f"A close {comparator} the nearest zone would put the next verified zone at {price_label(target)} in view.",
                "bias": result["bias"], "structure": result["structure"],
                "anchor": confirmed[-1].as_dict(), "vwap_at_creation": vwap, "quality": "Mixed" if opposing_bias or zone["observations"] < 2 else "Strong",
                "supporting": [zone, objective], "opposing_zone": opposing[0] if opposing else None,
                "conflicting": [f"Current bias is {result['bias'].lower()}."] if opposing_bias else [],
                "provenance": provenance,
            })
        result["reason"] = (
            "Waiting for a subsequent provider-confirmed five-minute close through the trigger zone."
            if len(proposals) == 2 else
            "A direction needs two verified zones beyond the current close to define both its trigger and target."
        )
        return result, proposals, confirmed
    # A timely after-close observation may contain the final regular-session bar.
    timely_close = not current and closing <= now <= closing + BAR and available >= closing
    return result, [], confirmed if fresh and timely_close else []
