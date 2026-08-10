from __future__ import annotations

from datetime import date, datetime

from modules.options_income import build_income_spread


def _mid(contract: dict) -> float | None:
    if contract.get("mid") is not None:
        return float(contract["mid"])
    bid = contract.get("bid")
    ask = contract.get("ask")
    if bid is None or ask is None:
        return None
    return (float(bid) + float(ask)) / 2


def _dte(expiration: str, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    parsed = datetime.strptime(expiration[:10], "%Y-%m-%d").date()
    return (parsed - as_of).days


def _contracts(chain: dict, option_type: str, underlying: float) -> list[dict]:
    key = "calls" if option_type == "Call" else "puts"
    rows = []
    for contract in chain.get(key, []):
        mid = _mid(contract)
        strike = contract.get("strike")
        if strike is None or mid is None or mid <= 0:
            continue
        rows.append({**contract, "mid": mid, "strike": float(strike)})
    return sorted(rows, key=lambda row: abs(row["strike"] - underlying))


def _by_delta(contracts: list[dict], target_delta: float) -> dict | None:
    if not contracts:
        return None
    return min(
        contracts,
        key=lambda row: (
            abs(abs(float(row.get("delta") or 0.0)) - target_delta),
            abs(float(row.get("ask") or row["mid"]) - float(row.get("bid") or row["mid"])),
        ),
    )


def _protection(
    contracts: list[dict],
    anchor: float,
    width: float,
    direction: str,
) -> dict | None:
    if direction == "higher":
        candidates = [row for row in contracts if row["strike"] > anchor]
        target = anchor + width
    else:
        candidates = [row for row in contracts if row["strike"] < anchor]
        target = anchor - width
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs(row["strike"] - target))


def _legs(*items: tuple[str, dict]) -> list[dict]:
    rows = []
    for action, contract in items:
        rows.append(
            {
                "action": action,
                "quantity": 1,
                "type": contract.get("type"),
                "strike": float(contract["strike"]),
                "contract": contract.get("contract"),
                "bid": contract.get("bid"),
                "ask": contract.get("ask"),
                "mid": contract.get("mid"),
                "delta": contract.get("delta"),
            }
        )
    return rows


def _format_price(value: float) -> str:
    return f"${value:,.2f}"


def _candidate(
    *,
    bucket: str,
    strategy: str,
    expiration: str,
    side: str,
    entry_price: float,
    max_profit: float | None,
    max_loss: float | None,
    breakeven: str,
    legs: list[dict],
    thesis: str,
    fit: str,
) -> dict:
    return {
        "bucket": bucket,
        "strategy": strategy,
        "expiration": expiration[:10],
        "expiration_note": f"{_dte(expiration)} DTE",
        "dte": _dte(expiration),
        "side": side,
        "entry_price": round(entry_price, 2),
        "net_credit": round(entry_price, 2) if "Credit" in side else 0.0,
        "target_width": 0.0,
        "actual_width": 0.0,
        "max_profit": round(max_profit, 2) if max_profit is not None else None,
        "max_loss": round(max_loss, 2) if max_loss is not None else None,
        "breakeven": breakeven,
        "legs": legs,
        "thesis": thesis,
        "fit": fit,
    }


def _debit_spread(
    chain: dict,
    underlying: float,
    outlook: str,
    bucket: str,
    width: float,
) -> dict | None:
    option_type = "Call" if outlook == "Bullish" else "Put"
    contracts = _contracts(chain, option_type, underlying)
    long_leg = _by_delta(contracts, 0.50)
    if long_leg is None:
        return None
    short_leg = _protection(
        contracts,
        long_leg["strike"],
        width,
        "higher" if option_type == "Call" else "lower",
    )
    if short_leg is None:
        return None
    debit = round(long_leg["mid"] - short_leg["mid"], 2)
    actual_width = abs(short_leg["strike"] - long_leg["strike"])
    if debit <= 0 or debit >= actual_width:
        return None
    max_profit = (actual_width - debit) * 100
    max_loss = debit * 100
    breakeven_value = (
        long_leg["strike"] + debit
        if option_type == "Call"
        else long_leg["strike"] - debit
    )
    strategy = "Call Debit Spread" if option_type == "Call" else "Put Debit Spread"
    candidate = _candidate(
        bucket=bucket,
        strategy=strategy,
        expiration=chain["expiration"],
        side="Long / Debit",
        entry_price=debit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven=_format_price(breakeven_value),
        legs=_legs(("Buy", long_leg), ("Sell", short_leg)),
        thesis=f"{outlook} directional structure with defined risk.",
        fit="Uses the selected expiration bucket and caps both risk and reward.",
    )
    candidate["actual_width"] = round(actual_width, 2)
    candidate["target_width"] = round(width, 2)
    return candidate


def _long_option(
    chain: dict,
    underlying: float,
    outlook: str,
    bucket: str,
    leaps: bool = False,
) -> dict | None:
    option_type = "Call" if outlook == "Bullish" else "Put"
    contracts = _contracts(chain, option_type, underlying)
    contract = _by_delta(contracts, 0.70 if leaps else 0.45)
    if contract is None:
        return None
    premium = round(contract["mid"], 2)
    if premium <= 0:
        return None
    breakeven_value = (
        contract["strike"] + premium
        if option_type == "Call"
        else contract["strike"] - premium
    )
    strategy = (
        f"LEAPS {option_type}" if leaps else f"Long {option_type}"
    )
    return _candidate(
        bucket=bucket,
        strategy=strategy,
        expiration=chain["expiration"],
        side="Long / Debit",
        entry_price=premium,
        max_profit=None,
        max_loss=premium * 100,
        breakeven=_format_price(breakeven_value),
        legs=_legs(("Buy", contract)),
        thesis=f"{outlook} directional exposure with uncapped upside before expiration.",
        fit="Best when movement and timing matter more than collecting premium.",
    )


def _iron_condor(
    chain: dict,
    underlying: float,
    bucket: str,
    width: float,
) -> dict | None:
    spread = build_income_spread(chain, underlying, "Neutral", bucket, spread_width=width)
    if not spread or spread["strategy"] != "Iron Condor":
        return None
    spread["side"] = "Short / Credit"
    spread["entry_price"] = spread["net_credit"]
    spread["thesis"] = "Neutral range thesis using both put and call credit spreads."
    spread["fit"] = "Best when the session is balanced and expected range is contained."
    return spread


def _butterfly(
    chain: dict,
    underlying: float,
    bucket: str,
    width: float,
) -> dict | None:
    contracts = _contracts(chain, "Call", underlying)
    center = min(contracts, key=lambda row: abs(row["strike"] - underlying)) if contracts else None
    if center is None:
        return None
    lower = _protection(contracts, center["strike"], width, "lower")
    upper = _protection(contracts, center["strike"], width, "higher")
    if lower is None or upper is None:
        return None
    debit = round(lower["mid"] + upper["mid"] - (2 * center["mid"]), 2)
    actual_width = min(center["strike"] - lower["strike"], upper["strike"] - center["strike"])
    if debit <= 0 or debit >= actual_width:
        return None
    max_profit = (actual_width - debit) * 100
    max_loss = debit * 100
    return _candidate(
        bucket=bucket,
        strategy="Call Butterfly",
        expiration=chain["expiration"],
        side="Long / Debit",
        entry_price=debit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven=f"{_format_price(lower['strike'] + debit)} to {_format_price(upper['strike'] - debit)}",
        legs=_legs(("Buy", lower), ("Sell", center), ("Sell", center), ("Buy", upper)),
        thesis="Defined target-zone trade around the center strike.",
        fit="Best when the expected move has a clear price magnet or range target.",
    )


def _straddle(
    chain: dict,
    underlying: float,
    bucket: str,
) -> dict | None:
    call = _by_delta(_contracts(chain, "Call", underlying), 0.50)
    put = _by_delta(_contracts(chain, "Put", underlying), 0.50)
    if call is None or put is None:
        return None
    debit = round(call["mid"] + put["mid"], 2)
    if debit <= 0:
        return None
    center = (call["strike"] + put["strike"]) / 2
    return _candidate(
        bucket=bucket,
        strategy="Long Straddle",
        expiration=chain["expiration"],
        side="Long / Debit",
        entry_price=debit,
        max_profit=None,
        max_loss=debit * 100,
        breakeven=f"{_format_price(center - debit)} to {_format_price(center + debit)}",
        legs=_legs(("Buy", call), ("Buy", put)),
        thesis="Volatility expansion idea when direction is uncertain.",
        fit="Requires a meaningful move; avoid if expected movement is muted.",
    )


def _calendar_placeholder(bucket: str, expiration: str, strategy: str) -> dict:
    return {
        "bucket": bucket,
        "strategy": strategy,
        "expiration": expiration[:10],
        "expiration_note": f"{_dte(expiration)} DTE",
        "dte": _dte(expiration),
        "side": "Insufficient chain structure",
        "entry_price": None,
        "net_credit": 0.0,
        "target_width": 0.0,
        "actual_width": 0.0,
        "max_profit": None,
        "max_loss": None,
        "breakeven": "Requires near and far expiration pricing",
        "legs": [],
        "thesis": "Supported as an analysis category, but needs multi-expiration pricing before displaying a priced trade.",
        "fit": "Use when timing, term structure, and volatility are the primary thesis.",
    }


def _leaps_expiration(expirations: list[str], as_of: date | None = None) -> str | None:
    as_of = as_of or date.today()
    candidates = [
        expiration
        for expiration in expirations
        if _dte(expiration, as_of) >= 181
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda expiration: abs(_dte(expiration, as_of) - 365))


def build_option_suggestions(
    chains: dict[str, dict],
    underlying: float,
    outlook: str,
    width: float,
    expirations: list[str],
    include_unpriced: bool = True,
) -> dict[str, list[dict]]:
    suggestions: dict[str, list[dict]] = {}
    for bucket, chain in chains.items():
        rows = []
        if outlook in {"Bullish", "Bearish"}:
            credit = build_income_spread(
                chain,
                underlying,
                outlook,
                bucket,
                spread_width=width,
            )
            if credit:
                credit["side"] = "Short / Credit"
                credit["entry_price"] = credit["net_credit"]
                credit["thesis"] = f"{outlook} income idea using defined risk."
                credit["fit"] = "Uses the same income-spread methodology from the prior tab."
                rows.append(credit)
            for builder in (
                lambda: _debit_spread(chain, underlying, outlook, bucket, width),
                lambda: _long_option(chain, underlying, outlook, bucket),
            ):
                candidate = builder()
                if candidate:
                    rows.append(candidate)
        condor = _iron_condor(chain, underlying, bucket, width)
        if condor:
            rows.append(condor)
        for builder in (
            lambda: _butterfly(chain, underlying, bucket, width),
            lambda: _straddle(chain, underlying, bucket),
        ):
            candidate = builder()
            if candidate:
                rows.append(candidate)
        if include_unpriced and bucket != "Day Trade":
            rows.append(_calendar_placeholder(bucket, chain["expiration"], "Calendar Spread"))
            rows.append(_calendar_placeholder(bucket, chain["expiration"], "Diagonal Spread"))
        suggestions[bucket] = rows

    leaps_expiration = _leaps_expiration(expirations)
    if leaps_expiration and outlook in {"Bullish", "Bearish"} and "LEAPS" in chains:
        leaps = _long_option(chains["LEAPS"], underlying, outlook, "LEAPS", leaps=True)
        if leaps:
            suggestions["LEAPS"] = [leaps]
    return suggestions


def suggestion_management_plan(suggestion: dict) -> list[dict]:
    entry = suggestion.get("entry_price")
    if entry is None:
        return [
            {
                "Rule": "Insufficient priced structure",
                "Trigger": "Do not take until near and far legs can be priced from the option chain",
                "Reason": "The app should not fabricate debit, credit, max loss, or breakeven.",
            }
        ]
    entry = float(entry)
    if suggestion.get("side") == "Short / Credit":
        profit_50 = round(entry * 0.50, 2)
        profit_75 = round(entry * 0.25, 2)
        stop_value = round(entry * 2.0, 2)
        return [
            {
                "Rule": "Credit profit target",
                "Trigger": f"Consider closing around ${profit_50:,.2f} to ${profit_75:,.2f}",
                "Reason": "Captures roughly 50-75% of credit before tail risk dominates remaining reward.",
            },
            {
                "Rule": "Credit spread stop",
                "Trigger": f"Exit or reduce if spread value reaches about ${stop_value:,.2f}",
                "Reason": "Prevents a premium idea from turning into a max-loss fight.",
            },
            {
                "Rule": "No final-dollars rule",
                "Trigger": "Do not hold only to collect a few remaining dollars while max risk remains large",
                "Reason": "Remaining reward can become too small relative to remaining risk.",
            },
        ]
    if "LEAPS" in suggestion.get("strategy", ""):
        stop_value = round(entry * 0.75, 2)
        return [
            {
                "Rule": "LEAPS thesis stop",
                "Trigger": "Review on weekly trend failure, major support loss, or thesis deterioration",
                "Reason": "A long-term option should not be managed from 5-minute noise.",
            },
            {
                "Rule": "Capital protection",
                "Trigger": f"Review if option value falls near ${stop_value:,.2f}",
                "Reason": "Keeps maximum acceptable loss visible without pretending it is a precise fill.",
            },
            {
                "Rule": "Roll review",
                "Trigger": "Review when DTE falls below 180 days",
                "Reason": "Long-term exposure may need more time if the thesis remains intact.",
            },
        ]
    target_1 = round(entry * 1.50, 2)
    target_2 = round(entry * 2.00, 2)
    stop_value = round(max(0.01, entry * 0.50), 2)
    return [
        {
            "Rule": "Debit stop",
            "Trigger": f"Exit or reduce near ${stop_value:,.2f} if underlying thesis fails",
            "Reason": "Chart invalidation leads; option price is only an estimate.",
        },
        {
            "Rule": "Target 1",
            "Trigger": f"Consider profit protection near ${target_1:,.2f}",
            "Reason": "Protects a winner before reversal risk takes back the move.",
        },
        {
            "Rule": "Target 2",
            "Trigger": f"Consider full exit or tight trail near ${target_2:,.2f}",
            "Reason": "Prevents holding for extra cents when momentum has already paid.",
        },
    ]
