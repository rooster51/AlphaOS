from __future__ import annotations

import pandas as pd


def _prepared(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    frame = history.sort_values("date").copy()
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["high", "low", "close"])
    if len(frame) < 22:
        return pd.DataFrame()

    close = frame["close"]
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["return_1d"] = close.pct_change()
    frame["return_5d"] = close.pct_change(5)
    frame["sma_20"] = close.rolling(20).mean()
    frame["atr_14"] = true_range.rolling(14).mean()
    frame["atr_pct"] = frame["atr_14"] / close
    frame["range_pct"] = (frame["high"] - frame["low"]) / close
    frame["avg_range_pct"] = frame["range_pct"].rolling(10).mean()
    frame["avg_volume_20"] = frame["volume"].rolling(20).mean()
    frame["volume_ratio"] = frame["volume"] / frame["avg_volume_20"]
    frame["prior_20d_high"] = frame["high"].shift(1).rolling(20).max()
    frame["prior_20d_low"] = frame["low"].shift(1).rolling(20).min()
    return frame.dropna(subset=["sma_20", "atr_pct"]).reset_index(drop=True)


def session_texture(history: pd.DataFrame, analysis: dict) -> dict:
    frame = _prepared(history)
    if frame.empty:
        return {
            "label": "Unknown",
            "status": "Unavailable",
            "detail": "Not enough history to classify the session setup.",
            "action": "Use smaller size and wait for live confirmation.",
        }

    latest = frame.iloc[-1]
    last = float(analysis.get("last") or latest["close"])
    change_pct = analysis.get("change_pct")
    change_pct = float(change_pct) if change_pct is not None else 0.0
    day_bias = analysis.get("day_bias") or analysis.get("outlook") or "Neutral"
    swing_outlook = analysis.get("swing_outlook") or analysis.get("outlook") or "Neutral"
    atr_pct = float(latest["atr_pct"] * 100)
    avg_range_pct = float(latest["avg_range_pct"] * 100)
    volume_ratio = latest.get("volume_ratio")
    volume_ratio = float(volume_ratio) if not pd.isna(volume_ratio) else None
    prior_high = float(latest["prior_20d_high"]) if not pd.isna(latest["prior_20d_high"]) else last
    prior_low = float(latest["prior_20d_low"]) if not pd.isna(latest["prior_20d_low"]) else last
    distance_to_high = ((prior_high / last) - 1) * 100 if last else 0.0
    distance_to_low = ((last / prior_low) - 1) * 100 if prior_low else 0.0
    compressed = avg_range_pct < atr_pct * 0.75 if atr_pct else False
    near_breakout = distance_to_high <= max(0.35, atr_pct * 0.35)
    near_breakdown = distance_to_low <= max(0.35, atr_pct * 0.35)
    conflicting = day_bias != "Neutral" and swing_outlook != "Neutral" and day_bias != swing_outlook

    if compressed and abs(change_pct) < max(0.25, atr_pct * 0.25):
        return {
            "label": "Choppy / Compressed",
            "status": "Caution",
            "detail": "Recent range is compressed and today's move is muted, which can punish fast entries and emotional re-entries.",
            "action": "Wait for a clean break or reduce spread size; avoid panic flipping after small moves.",
        }
    if conflicting:
        return {
            "label": "Mixed Tape",
            "status": "Caution",
            "detail": "Day bias and swing backdrop disagree, so a reversal or fake-out is more likely.",
            "action": "Favor smaller size, wider confirmation, or skip until direction resolves.",
        }
    if near_breakout and change_pct > 0 and day_bias == "Bullish":
        return {
            "label": "Breakout Setup",
            "status": "Directional",
            "detail": "Price is pressing near the recent high with bullish day confirmation.",
            "action": "Do not sell into breakout strength without a clear invalidation level.",
        }
    if near_breakdown and change_pct < 0 and day_bias == "Bearish":
        return {
            "label": "Breakdown Setup",
            "status": "Directional",
            "detail": "Price is pressing near the recent low with bearish day confirmation.",
            "action": "Avoid bullish income spreads unless the breakdown fails first.",
        }
    return {
        "label": "Balanced Trend",
        "status": "Normal",
        "detail": "No major chop or breakout warning is visible from the current daily context.",
        "action": "Use the planned stop and profit target rather than reacting to noise.",
    }


def spread_management_plan(spread: dict, analysis: dict) -> list[dict]:
    credit = float(spread.get("net_credit") or 0.0)
    max_loss = float(spread.get("max_loss") or 0.0)
    legs = spread.get("legs", [])
    short_puts = [
        float(leg["strike"])
        for leg in legs
        if leg.get("action") == "Sell" and leg.get("type") == "Put"
    ]
    short_calls = [
        float(leg["strike"])
        for leg in legs
        if leg.get("action") == "Sell" and leg.get("type") == "Call"
    ]
    profit_take = round(credit * 0.5, 2)
    premium_stop = round(credit * 2.0, 2)
    max_loss_stop = round(max_loss * 0.5, 2)
    rows = [
        {
            "Rule": "Profit target",
            "Trigger": f"Buy back at ${profit_take:,.2f} or less",
            "Reason": "Take roughly 50% of credit before the position can reverse.",
        },
        {
            "Rule": "Premium stop",
            "Trigger": f"Exit if spread value reaches about ${premium_stop:,.2f}",
            "Reason": "Prevents a small income trade from turning into a max-loss fight.",
        },
        {
            "Rule": "Dollar stop",
            "Trigger": f"Exit or reduce at about ${max_loss_stop:,.2f} loss per spread",
            "Reason": "Keeps the loss decision mechanical instead of emotional.",
        },
    ]
    if short_puts:
        short_put = max(short_puts)
        rows.append(
            {
                "Rule": "Bullish invalidation",
                "Trigger": f"Underlying loses the short put near ${short_put:,.2f}",
                "Reason": "The bullish income thesis is no longer clean.",
            }
        )
    if short_calls:
        short_call = min(short_calls)
        rows.append(
            {
                "Rule": "Bearish invalidation",
                "Trigger": f"Underlying breaks the short call near ${short_call:,.2f}",
                "Reason": "The bearish income thesis is no longer clean.",
            }
        )
    rows.append(
        {
            "Rule": "No revenge rule",
            "Trigger": "After a stop, do not open the opposite trade for 30 minutes",
            "Reason": "Stops panic selling followed by panic buying to erase the first loss.",
        }
    )
    return rows
