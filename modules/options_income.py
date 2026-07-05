from __future__ import annotations

from datetime import date, datetime


BUCKET_TARGET_DAYS = {
    "Day Trade": 0,
    "Weekly": 7,
    "Monthly": 30,
}

BUCKET_WIDTH_PCT = {
    "Day Trade": 0.005,
    "Weekly": 0.015,
    "Monthly": 0.03,
}


def select_expiration_buckets(
    expirations: list[str],
    as_of: date | None = None,
) -> dict[str, str]:
    as_of = as_of or date.today()
    parsed = sorted(
        {
            datetime.strptime(value[:10], "%Y-%m-%d").date()
            for value in expirations
            if value
        }
    )
    available = [expiration for expiration in parsed if expiration >= as_of]
    if not available:
        return {}

    selected = {}
    for label, target_days in BUCKET_TARGET_DAYS.items():
        candidates = available
        if label == "Monthly":
            standard_monthlies = [
                expiration
                for expiration in available
                if expiration.weekday() == 4
                and 15 <= expiration.day <= 21
                and 7 <= (expiration - as_of).days <= 60
            ]
            if standard_monthlies:
                candidates = standard_monthlies
        best = min(
            candidates,
            key=lambda expiration: (
                abs((expiration - as_of).days - target_days),
                (expiration - as_of).days,
            ),
        )
        selected[label] = best.isoformat()
    return selected


def _mid(contract: dict) -> float | None:
    if contract.get("mid") is not None:
        return float(contract["mid"])
    bid = contract.get("bid")
    ask = contract.get("ask")
    if bid is None or ask is None:
        return None
    return (float(bid) + float(ask)) / 2


def _liquid_contracts(contracts: list[dict], underlying: float, kind: str) -> list[dict]:
    rows = []
    for contract in contracts:
        strike = contract.get("strike")
        bid = contract.get("bid")
        ask = contract.get("ask")
        if strike is None or bid is None or ask is None:
            continue
        if float(ask) <= 0 or float(bid) < 0:
            continue
        if kind == "put" and float(strike) >= underlying:
            continue
        if kind == "call" and float(strike) <= underlying:
            continue
        rows.append(contract)
    return rows


def _pick_short(
    contracts: list[dict],
    underlying: float,
    kind: str,
    target_delta: float,
) -> dict | None:
    candidates = _liquid_contracts(contracts, underlying, kind)
    if not candidates:
        return None

    target_price = underlying * (0.99 if kind == "put" else 1.01)

    def score(contract: dict) -> tuple[float, float]:
        delta = contract.get("delta")
        delta_score = (
            abs(abs(float(delta)) - target_delta)
            if delta is not None
            else 1.0
        )
        spread = float(contract["ask"]) - float(contract["bid"])
        mid = _mid(contract) or 0.01
        spread_ratio = spread / mid
        price_score = abs(float(contract["strike"]) - target_price) / underlying
        return delta_score + (spread_ratio * 0.05), price_score

    return min(candidates, key=score)


def _pick_protection(
    contracts: list[dict],
    short_strike: float,
    target_width: float,
    kind: str,
) -> dict | None:
    candidates = [
        contract
        for contract in contracts
        if contract.get("strike") is not None
        and contract.get("ask") is not None
        and float(contract["ask"]) > 0
        and (
            float(contract["strike"]) < short_strike
            if kind == "put"
            else float(contract["strike"]) > short_strike
        )
    ]
    if not candidates:
        return None
    target = (
        short_strike - target_width
        if kind == "put"
        else short_strike + target_width
    )
    return min(candidates, key=lambda contract: abs(float(contract["strike"]) - target))


def _credit_leg_pair(
    contracts: list[dict],
    underlying: float,
    kind: str,
    width_pct: float,
    target_delta: float,
) -> dict | None:
    short = _pick_short(contracts, underlying, kind, target_delta)
    if short is None:
        return None
    long = _pick_protection(
        contracts,
        float(short["strike"]),
        underlying * width_pct,
        kind,
    )
    if long is None:
        return None
    short_mid = _mid(short)
    long_mid = _mid(long)
    if short_mid is None or long_mid is None:
        return None
    credit = round(short_mid - long_mid, 2)
    width = abs(float(short["strike"]) - float(long["strike"]))
    if credit <= 0 or credit >= width:
        return None
    return {
        "credit": credit,
        "width": width,
        "short": short,
        "long": long,
    }


def build_income_spread(
    chain: dict,
    underlying: float,
    outlook: str,
    bucket: str,
    as_of: date | None = None,
) -> dict | None:
    as_of = as_of or date.today()
    expiration = datetime.strptime(chain["expiration"][:10], "%Y-%m-%d").date()
    dte = (expiration - as_of).days
    width_pct = BUCKET_WIDTH_PCT[bucket]
    target_delta = 0.20 if bucket == "Day Trade" else 0.25

    put_pair = _credit_leg_pair(
        chain.get("puts", []),
        underlying,
        "put",
        width_pct,
        target_delta,
    )
    call_pair = _credit_leg_pair(
        chain.get("calls", []),
        underlying,
        "call",
        width_pct,
        target_delta,
    )

    if outlook == "Bullish":
        strategy = "Bull Put Credit Spread"
        pairs = [put_pair] if put_pair else []
    elif outlook == "Bearish":
        strategy = "Bear Call Credit Spread"
        pairs = [call_pair] if call_pair else []
    else:
        strategy = "Iron Condor"
        pairs = [pair for pair in (put_pair, call_pair) if pair]
        if len(pairs) < 2:
            strategy = (
                "Bull Put Credit Spread"
                if put_pair
                else "Bear Call Credit Spread"
            )

    if not pairs:
        return None

    credit = round(sum(pair["credit"] for pair in pairs), 2)
    max_width = max(pair["width"] for pair in pairs)
    max_loss = round((max_width - credit) * 100, 2)
    legs = []
    for pair in pairs:
        option_type = pair["short"]["type"]
        legs.extend(
            [
                {
                    "action": "Sell",
                    "quantity": 1,
                    "type": option_type,
                    "strike": float(pair["short"]["strike"]),
                    "contract": pair["short"]["contract"],
                    "mid": _mid(pair["short"]),
                    "delta": pair["short"].get("delta"),
                },
                {
                    "action": "Buy",
                    "quantity": 1,
                    "type": option_type,
                    "strike": float(pair["long"]["strike"]),
                    "contract": pair["long"]["contract"],
                    "mid": _mid(pair["long"]),
                    "delta": pair["long"].get("delta"),
                },
            ]
        )

    short_put = put_pair["short"]["strike"] if put_pair else None
    short_call = call_pair["short"]["strike"] if call_pair else None
    if strategy == "Iron Condor":
        breakeven = (
            f"${float(short_put) - credit:,.2f} to "
            f"${float(short_call) + credit:,.2f}"
        )
    elif put_pair:
        breakeven = f"${float(short_put) - credit:,.2f}"
    else:
        breakeven = f"${float(short_call) + credit:,.2f}"

    expiration_note = (
        "Same-day expiration"
        if dte == 0
        else f"Nearest listed expiration ({dte} DTE)"
        if bucket == "Day Trade"
        else f"{dte} DTE"
    )
    return {
        "bucket": bucket,
        "strategy": strategy,
        "expiration": expiration.isoformat(),
        "expiration_note": expiration_note,
        "dte": dte,
        "net_credit": credit,
        "max_profit": round(credit * 100, 2),
        "max_loss": max_loss,
        "breakeven": breakeven,
        "legs": legs,
    }
