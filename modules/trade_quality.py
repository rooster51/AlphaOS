from __future__ import annotations


QUALITY_DEFAULTS = {
    "min_trade_quality_score": 70.0,
    "max_bid_ask_pct": 18.0,
    "max_account_risk_pct": 2.0,
    "block_choppy_day_trades": True,
    "block_conflicting_trend": True,
    "require_positive_backtest": True,
}


def normalize_quality_settings(settings: dict | None) -> dict:
    settings = settings or {}
    quality = dict(QUALITY_DEFAULTS)
    for key in quality:
        if settings.get(key) is not None:
            quality[key] = settings[key]
    quality["min_trade_quality_score"] = float(
        quality["min_trade_quality_score"] or 0.0
    )
    quality["max_bid_ask_pct"] = float(quality["max_bid_ask_pct"] or 0.0)
    quality["max_account_risk_pct"] = float(
        quality["max_account_risk_pct"] or 0.0
    )
    quality["block_choppy_day_trades"] = bool(quality["block_choppy_day_trades"])
    quality["block_conflicting_trend"] = bool(quality["block_conflicting_trend"])
    quality["require_positive_backtest"] = bool(quality["require_positive_backtest"])
    return quality


def _direction_from_strategy(strategy: str, side: str = "") -> str:
    text = f"{strategy} {side}".lower()
    if "condor" in text or "straddle" in text or "butterfly" in text:
        return "Neutral"
    if "put credit" in text or "call debit" in text or "long call" in text or "leaps call" in text:
        return "Bullish"
    if "call credit" in text or "put debit" in text or "long put" in text or "leaps put" in text:
        return "Bearish"
    return "Neutral"


def _option_liquidity(legs: list[dict]) -> dict:
    widest_pct = 0.0
    missing_prices = 0
    checked = 0
    for leg in legs:
        bid = leg.get("bid")
        ask = leg.get("ask")
        mid = leg.get("mid")
        if bid is None or ask is None:
            missing_prices += 1
            continue
        bid = float(bid)
        ask = float(ask)
        mid = float(mid if mid is not None else (bid + ask) / 2)
        if mid <= 0:
            missing_prices += 1
            continue
        checked += 1
        widest_pct = max(widest_pct, ((ask - bid) / mid) * 100)
    return {
        "checked": checked,
        "missing_prices": missing_prices,
        "widest_bid_ask_pct": round(widest_pct, 2),
    }


def _add_check(rows: list[dict], name: str, status: str, detail: str) -> None:
    rows.append({"Check": name, "Status": status, "Detail": detail})


def _status(score: float, blockers: list[str], warnings: list[str]) -> str:
    if blockers:
        return "Blocked"
    if score >= 82 and not warnings:
        return "Approved"
    return "Caution"


def evaluate_trade_quality(
    *,
    symbol: str,
    strategy: str,
    side: str = "",
    bucket: str = "",
    legs: list[dict] | None = None,
    entry_price: float | None = None,
    max_loss: float | None = None,
    analysis: dict | None = None,
    session: dict | None = None,
    reversal_checks: list[dict] | None = None,
    backtest: dict | None = None,
    discipline: dict | None = None,
    settings: dict | None = None,
) -> dict:
    quality = normalize_quality_settings(settings)
    rows: list[dict] = []
    blockers: list[str] = []
    warnings: list[str] = []
    score = 100.0
    legs = legs or []
    direction = _direction_from_strategy(strategy, side)
    day_trade = "day" in bucket.lower()

    if not analysis:
        blockers.append("Market analysis is unavailable.")
        score -= 30
        _add_check(rows, "Market data", "Block", "No live or historical context is available.")
    else:
        outlook = analysis.get("outlook") or "Neutral"
        day_bias = analysis.get("day_bias") or outlook
        swing = analysis.get("swing_outlook") or outlook
        if direction != "Neutral" and outlook != "Neutral" and direction != outlook:
            blockers.append(f"{strategy} is {direction}, but the active outlook is {outlook}.")
            score -= 25
            _add_check(rows, "Trend alignment", "Block", "Strategy direction conflicts with active trend.")
        elif direction != "Neutral" and day_bias != "Neutral" and direction != day_bias:
            warnings.append(f"Day bias is {day_bias}, which conflicts with {direction} trade direction.")
            score -= 12
            _add_check(rows, "Day bias", "Warn", "Intraday bias conflicts with the proposed direction.")
        else:
            _add_check(rows, "Trend alignment", "Pass", "Strategy direction does not conflict with active trend.")

        if (
            quality["block_conflicting_trend"]
            and day_bias != "Neutral"
            and swing != "Neutral"
            and day_bias != swing
        ):
            blockers.append(f"Day bias ({day_bias}) and swing backdrop ({swing}) disagree.")
            score -= 20
            _add_check(rows, "Timeframe agreement", "Block", "Day trend and swing trend disagree.")
        else:
            _add_check(rows, "Timeframe agreement", "Pass", "No hard day/swing conflict detected.")

    session = session or {}
    if session.get("label") in {"Choppy / Compressed", "Mixed Tape"}:
        detail = session.get("detail") or "Session texture is not clean."
        if day_trade and quality["block_choppy_day_trades"]:
            blockers.append(f"{session['label']} is blocked for day trades.")
            score -= 22
            _add_check(rows, "Session texture", "Block", detail)
        else:
            warnings.append(detail)
            score -= 10
            _add_check(rows, "Session texture", "Warn", detail)
    elif session.get("status") == "Directional" and direction == "Neutral":
        warnings.append("Directional session can punish neutral premium structures.")
        score -= 10
        _add_check(rows, "Session texture", "Warn", "Neutral strategy during a directional tape.")
    else:
        _add_check(rows, "Session texture", "Pass", session.get("detail") or "No session warning detected.")

    liquidity = _option_liquidity(legs)
    if legs and liquidity["missing_prices"]:
        warnings.append("One or more option legs are missing bid/ask pricing.")
        score -= 8
        _add_check(rows, "Options liquidity", "Warn", "Some legs are missing bid/ask pricing.")
    elif legs and quality["max_bid_ask_pct"] and liquidity["widest_bid_ask_pct"] > quality["max_bid_ask_pct"]:
        blockers.append(
            f"Bid/ask spread is too wide: {liquidity['widest_bid_ask_pct']:.1f}% versus {quality['max_bid_ask_pct']:.1f}% max."
        )
        score -= 18
        _add_check(rows, "Options liquidity", "Block", "Bid/ask spread is wider than your rule allows.")
    elif legs:
        _add_check(rows, "Options liquidity", "Pass", f"Widest bid/ask spread is {liquidity['widest_bid_ask_pct']:.1f}%.")
    else:
        warnings.append("No priced option legs are attached to this idea.")
        score -= 12
        _add_check(rows, "Options liquidity", "Warn", "No priced legs are available to check.")

    warning_count = sum(1 for check in reversal_checks or [] if check.get("status") == "Warning")
    if warning_count >= 2:
        blockers.append(f"Reversal diagnostics show {warning_count} warnings.")
        score -= 20
        _add_check(rows, "Reversal risk", "Block", "Multiple reversal warnings are active.")
    elif warning_count == 1:
        warnings.append("One reversal warning is active.")
        score -= 8
        _add_check(rows, "Reversal risk", "Warn", "One reversal warning is active.")
    else:
        _add_check(rows, "Reversal risk", "Pass", "No major reversal warning is active.")

    if backtest and int(backtest.get("trades") or 0) > 0:
        win_rate = float(backtest.get("win_rate") or 0.0)
        avg_return = float(backtest.get("average_return") or 0.0)
        if quality["require_positive_backtest"] and avg_return <= 0:
            blockers.append(f"Backtest average return is not positive: {avg_return:+.2f}%.")
            score -= 18
            _add_check(rows, "Backtest edge", "Block", "Historical signal average return is not positive.")
        elif win_rate < float((settings or {}).get("min_backtest_win_rate") or 50.0):
            warnings.append(f"Backtest win rate is low at {win_rate:.1f}%.")
            score -= 10
            _add_check(rows, "Backtest edge", "Warn", "Win rate is below your threshold.")
        else:
            _add_check(rows, "Backtest edge", "Pass", f"Win rate {win_rate:.1f}%, average return {avg_return:+.2f}%.")
    else:
        warnings.append("Backtest has too few matching historical signals.")
        score -= 8
        _add_check(rows, "Backtest edge", "Warn", "Too few matching historical signals.")

    discipline = discipline or {}
    for blocker in discipline.get("blockers", []):
        blockers.append(blocker)
        score -= 15
    for warning in discipline.get("warnings", []):
        warnings.append(warning)
        score -= 6
    if discipline.get("status") == "Clear":
        _add_check(rows, "Account guardrails", "Pass", "Account-state guardrails are clear.")
    elif discipline.get("status") == "Blocked":
        _add_check(rows, "Account guardrails", "Block", "One or more account-state guardrails are blocking.")
    elif discipline:
        _add_check(rows, "Account guardrails", "Warn", "Account-state guardrails require caution.")

    account_size = float((settings or {}).get("default_account_size") or 0.0)
    if max_loss is not None and account_size > 0:
        risk_pct = (float(max_loss) / account_size) * 100
        if quality["max_account_risk_pct"] and risk_pct > quality["max_account_risk_pct"]:
            blockers.append(
                f"Max loss is {risk_pct:.2f}% of account versus {quality['max_account_risk_pct']:.2f}% max."
            )
            score -= 18
            _add_check(rows, "Position risk", "Block", "Max loss exceeds your per-trade account risk cap.")
        else:
            _add_check(rows, "Position risk", "Pass", f"Max loss is about {risk_pct:.2f}% of account.")
    elif max_loss is None:
        warnings.append("Max loss is unknown or open-ended.")
        score -= 8
        _add_check(rows, "Position risk", "Warn", "Max loss is unknown or open-ended.")

    score = max(0.0, min(100.0, score))
    if score < quality["min_trade_quality_score"]:
        blockers.append(
            f"Quality score {score:.0f} is below your minimum of {quality['min_trade_quality_score']:.0f}."
        )

    return {
        "symbol": symbol.upper(),
        "strategy": strategy,
        "direction": direction,
        "score": round(score, 0),
        "status": _status(score, blockers, warnings),
        "blockers": blockers,
        "warnings": warnings,
        "checks": rows,
        "quality_settings": quality,
    }


def quality_badge_text(quality: dict) -> str:
    return f"{quality['status']} - {quality['score']:.0f}/100"
