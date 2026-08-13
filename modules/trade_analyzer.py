from __future__ import annotations

from datetime import date, datetime
import re


HORIZON_DTE_RANGES = {
    "DAY TRADE": (0, 2),
    "WEEKLY": (3, 14),
    "MONTHLY": (15, 60),
    "POSITION": (61, 180),
    "LEAPS": (181, 9999),
}

HORIZON_TIMEFRAMES = {
    "DAY TRADE": ["15m primary", "5m confirmation", "1h/daily context"],
    "WEEKLY": ["1h primary", "15m/30m confirmation", "daily context"],
    "MONTHLY": ["daily primary", "4h confirmation", "weekly context"],
    "POSITION": ["daily primary", "weekly context", "monthly macro context"],
    "LEAPS": ["weekly primary", "daily secondary", "monthly macro context"],
}

DEBIT_STRATEGIES = {
    "Call Debit Spread",
    "Put Debit Spread",
}

CREDIT_STRATEGIES = {
    "Bull Put Credit Spread",
    "Bear Call Credit Spread",
}


def expiration_to_dte(expiration: date | str | None, as_of: date | None = None) -> int | None:
    if expiration is None:
        return None
    as_of = as_of or date.today()
    if isinstance(expiration, str):
        try:
            expiration = datetime.strptime(expiration[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return max(0, (expiration - as_of).days)


def classify_horizon(selection: str, dte: int | None) -> str:
    if selection != "AUTO-DETECT":
        return selection
    if dte is None:
        return "WEEKLY"
    for horizon, (low, high) in HORIZON_DTE_RANGES.items():
        if low <= dte <= high:
            return horizon
    return "LEAPS"


def parse_option_legs(raw_legs: str) -> list[dict]:
    legs = []
    for line in raw_legs.splitlines():
        text = line.strip()
        if not text:
            continue
        action = "Buy" if re.search(r"\bbuy\b|\blong\b|\+", text, re.I) else "Sell"
        strike_match = re.search(r"(\d+(?:\.\d+)?)\s*([CP])\b", text, re.I)
        if strike_match:
            strike = float(strike_match.group(1))
            option_type = "Call" if strike_match.group(2).upper() == "C" else "Put"
        else:
            strike = None
            option_type = "Call" if "call" in text.lower() else "Put" if "put" in text.lower() else "Unknown"
        legs.append(
            {
                "Action": action,
                "Type": option_type,
                "Strike": strike,
                "Raw": text,
            }
        )
    return legs


def strategy_direction(strategy: str) -> str:
    if strategy in {"Call Debit Spread", "Bull Put Credit Spread"}:
        return "Bullish"
    if strategy in {"Put Debit Spread", "Bear Call Credit Spread"}:
        return "Bearish"
    return "Neutral"


def _spread_width(legs: list[dict]) -> float | None:
    strikes = sorted(
        float(leg["Strike"])
        for leg in legs
        if leg.get("Strike") is not None
    )
    if len(strikes) < 2:
        return None
    return max(strikes) - min(strikes)


def trade_risk_metrics(
    strategy: str,
    legs: list[dict],
    premium: float,
    contracts: int,
    account_balance: float,
    risk_pct: float,
    risk_dollar_limit: float,
) -> dict:
    contracts = max(1, int(contracts))
    width = _spread_width(legs)
    premium = max(0.0, float(premium))
    credit = premium if strategy in CREDIT_STRATEGIES else 0.0
    debit = premium if strategy not in CREDIT_STRATEGIES else 0.0

    if strategy in CREDIT_STRATEGIES:
        max_profit = credit * 100 * contracts
        max_loss = ((width - credit) * 100 * contracts) if width else None
        capital_required = max_loss
    elif "Spread" in strategy and width:
        max_loss = debit * 100 * contracts
        max_profit = max(0.0, (width - debit) * 100 * contracts)
        capital_required = max_loss
    elif strategy == "Butterfly" and width:
        max_loss = debit * 100 * contracts
        max_profit = max(0.0, (width - debit) * 100 * contracts)
        capital_required = max_loss
    else:
        max_loss = debit * 100 * contracts
        max_profit = None
        capital_required = max_loss

    planned_loss_cap = min(
        account_balance * (risk_pct / 100),
        risk_dollar_limit,
    )
    planned_loss = min(planned_loss_cap, max_loss) if max_loss is not None else planned_loss_cap
    account_committed_pct = (
        (capital_required / account_balance) * 100
        if account_balance and capital_required is not None
        else 0.0
    )
    account_planned_risk_pct = (
        (planned_loss / account_balance) * 100 if account_balance else 0.0
    )
    reward_risk = (
        max_profit / planned_loss
        if max_profit is not None and planned_loss
        else None
    )
    if account_committed_pct <= 5:
        risk_class = "LOW ACCOUNT RISK"
    elif account_committed_pct <= 10:
        risk_class = "MODERATE"
    elif account_committed_pct <= 20:
        risk_class = "HIGH"
    elif account_committed_pct <= 50:
        risk_class = "VERY HIGH"
    else:
        risk_class = "EXTREME"

    return {
        "capital_required": round(float(capital_required or 0.0), 2),
        "planned_loss": round(float(planned_loss), 2),
        "max_loss": round(float(max_loss or 0.0), 2),
        "max_profit": round(float(max_profit), 2) if max_profit is not None else None,
        "account_committed_pct": round(float(account_committed_pct), 2),
        "account_planned_risk_pct": round(float(account_planned_risk_pct), 2),
        "reward_risk": round(float(reward_risk), 2) if reward_risk is not None else None,
        "risk_class": risk_class,
        "width": round(float(width), 2) if width else None,
    }


def exit_plan(
    strategy: str,
    analysis: dict,
    premium: float,
    planned_loss: float,
    horizon: str,
) -> dict:
    last = analysis.get("last")
    atr_pct = float(analysis.get("atr_pct") or 0.0)
    if not last or not atr_pct:
        return {
            "available": False,
            "reason": "INSUFFICIENT EXIT STRUCTURE - underlying price or ATR is unavailable.",
        }
    direction = strategy_direction(strategy)
    atr_dollars = float(last) * (atr_pct / 100)
    if horizon == "DAY TRADE":
        stop_mult, target1_mult, target2_mult = 0.35, 0.50, 0.90
        time_stop = "Exit or reduce if the setup has not progressed after 2-4 five-minute candles."
    elif horizon == "WEEKLY":
        stop_mult, target1_mult, target2_mult = 0.90, 1.25, 2.00
        time_stop = "Reassess if the thesis has not progressed after 2-3 sessions."
    elif horizon in {"MONTHLY", "POSITION"}:
        stop_mult, target1_mult, target2_mult = 1.50, 2.00, 3.50
        time_stop = "Review weekly, before earnings, and when DTE enters a faster-theta zone."
    else:
        stop_mult, target1_mult, target2_mult = 2.50, 4.00, 7.00
        time_stop = "Review monthly, after earnings, and when DTE falls below 180 days."

    if direction == "Bearish":
        invalidation = float(last) + (atr_dollars * stop_mult)
        target1 = float(last) - (atr_dollars * target1_mult)
        target2 = float(last) - (atr_dollars * target2_mult)
        entry = f"Underlying below ${float(last):,.2f} after bearish confirmation"
    elif direction == "Bullish":
        invalidation = float(last) - (atr_dollars * stop_mult)
        target1 = float(last) + (atr_dollars * target1_mult)
        target2 = float(last) + (atr_dollars * target2_mult)
        entry = f"Underlying above ${float(last):,.2f} after bullish confirmation"
    else:
        invalidation = None
        target1 = float(last) + (atr_dollars * 0.75)
        target2 = float(last) - (atr_dollars * 0.75)
        entry = "Enter only if price remains inside the planned range and spread pricing is valid"

    option_stop = max(0.01, premium - (planned_loss / 100))
    return {
        "available": True,
        "entry": entry,
        "underlying_invalidation": (
            f"${invalidation:,.2f}" if invalidation is not None else "Range break on either side"
        ),
        "estimated_option_stop": f"${option_stop:,.2f}",
        "planned_loss": f"${planned_loss:,.2f}",
        "target_1": f"${target1:,.2f}",
        "target_2": f"${target2:,.2f}",
        "profit_plan": "One contract: consider full exit at Target 1, or hold for Target 2 only if momentum remains confirmed.",
        "breakeven_rule": "Move stop toward breakeven only after Target 1 or confirmed new structure.",
        "time_stop": time_stop,
        "early_exit": "Exit early if the original setup fails, VWAP/structure breaks, or momentum flips against the thesis.",
        "eod": "Mandatory end-of-day exit only for DAY TRADE positions.",
    }


def analyze_trade(
    symbol: str,
    strategy: str,
    horizon_selection: str,
    expiration: date | None,
    legs_text: str,
    premium: float,
    contracts: int,
    account_balance: float,
    risk_pct: float,
    risk_dollar_limit: float,
    analysis: dict | None,
    session: dict | None = None,
) -> dict:
    dte = expiration_to_dte(expiration)
    horizon = classify_horizon(horizon_selection, dte)
    legs = parse_option_legs(legs_text)
    risk = trade_risk_metrics(
        strategy,
        legs,
        premium,
        contracts,
        account_balance,
        risk_pct,
        risk_dollar_limit,
    )
    blockers = []
    warnings = []
    score = 70
    if analysis is None:
        blockers.append("INSUFFICIENT DATA - live quote or historical context is unavailable.")
    if not legs:
        blockers.append("INSUFFICIENT DATA - enter at least one option leg.")
    if (
        strategy in CREDIT_STRATEGIES
        or "Spread" in strategy
        or strategy == "Butterfly"
    ) and risk["width"] is None:
        blockers.append("INSUFFICIENT DATA - spread strategies require at least two valid strikes.")
    if risk["capital_required"] > account_balance:
        blockers.append("Capital required is greater than account balance.")
    if risk["account_committed_pct"] > 50:
        blockers.append("Account exposure is above 50%.")
    elif risk["account_committed_pct"] > 20:
        warnings.append("Account exposure is very high for one trade.")
        score -= 20
    if risk["reward_risk"] is not None and risk["reward_risk"] < 1:
        blockers.append("Realistic reward/risk is below 1.0.")
    if session and session.get("label") in {"Choppy / Compressed", "Mixed Tape"} and horizon == "DAY TRADE":
        blockers.append(f"{session['label']} is not clean enough for a day-trade entry.")
    if dte is not None:
        low, high = HORIZON_DTE_RANGES[horizon]
        if not low <= dte <= high:
            warnings.append(f"Expiration has {dte} DTE, which does not neatly fit {horizon}.")
            score -= 10

    plan = (
        exit_plan(strategy, analysis, premium, risk["planned_loss"], horizon)
        if analysis
        else {"available": False, "reason": "INSUFFICIENT EXIT STRUCTURE - analysis unavailable."}
    )
    if not plan.get("available"):
        blockers.append(plan["reason"])

    if blockers:
        verdict = "DO NOT TAKE"
        score = min(score, 35)
    elif score >= 85:
        verdict = "EXCELLENT SETUP"
    elif score >= 75:
        verdict = "GOOD SETUP"
    elif score >= 65:
        verdict = "ACCEPTABLE"
    elif score >= 50:
        verdict = "MODERATE RISK"
    else:
        verdict = "LOW PROBABILITY"

    return {
        "symbol": symbol.strip().upper(),
        "strategy": strategy,
        "horizon": horizon,
        "dte": dte,
        "timeframes": HORIZON_TIMEFRAMES[horizon],
        "direction": strategy_direction(strategy),
        "verdict": verdict,
        "score": max(0, min(100, score)),
        "risk": risk,
        "legs": legs,
        "exit_plan": plan,
        "blockers": blockers,
        "warnings": warnings,
    }


def growth_engine_plan(
    current_value: float,
    target_value: float,
    target_days: int,
    risk_per_trade: float,
    trades_per_week: int,
    average_r: float,
) -> dict:
    gap = max(0.0, target_value - current_value)
    daily_needed = gap / target_days if target_days else 0.0
    daily_pct = (
        ((target_value / current_value) ** (1 / target_days) - 1) * 100
        if current_value > 0 and target_value > current_value and target_days > 0
        else 0.0
    )
    weekly_needed = daily_needed * 5
    weekly_risk_budget = current_value * (risk_per_trade / 100) * max(1, trades_per_week)
    expected_weekly_profit = (
        current_value * (risk_per_trade / 100) * average_r * max(1, trades_per_week)
    )
    if expected_weekly_profit >= weekly_needed and gap > 0:
        posture = "PLAN IS MATHEMATICALLY PLAUSIBLE"
    elif gap == 0:
        posture = "TARGET ALREADY MET"
    else:
        posture = "TARGET REQUIRES MORE EDGE, MORE TIME, OR LESS AGGRESSIVE GOAL"
    return {
        "gap": round(gap, 2),
        "daily_needed": round(daily_needed, 2),
        "daily_pct": round(daily_pct, 2),
        "weekly_needed": round(weekly_needed, 2),
        "weekly_risk_budget": round(weekly_risk_budget, 2),
        "expected_weekly_profit": round(expected_weekly_profit, 2),
        "posture": posture,
    }
