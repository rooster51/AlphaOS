"""Identity and pricing gates for the explicitly dated ETF chain."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
from math import isfinite
import re

from modules.options_payoff import trade_analysis
from modules.quote_freshness import normalize_timestamp

MAX_AGE_SECONDS = 30
UNDERLYING_MAX_AGE_SECONDS = 15


def contract_identity(leg, symbol, expiration):
    match = re.fullmatch(r"([A-Z]+) *(\d{6})([CP])(\d{8})", leg.get("contract") or "")
    if not match:
        return False
    root, day, right, strike = match.groups()
    return (root == symbol and day == expiration[2:].replace("-", "")
            and right == {"Call": "C", "Put": "P"}.get(leg.get("type"))
            and int(strike) / 1000 == leg.get("strike") and int(strike) > 0)


def assess_contracts(legs, symbol, expiration, now, retrieved_at):
    retrieved = datetime.fromisoformat(retrieved_at)
    identifiers = Counter(leg["contract"] for leg in legs)
    strikes = Counter((leg["type"], leg["strike"]) for leg in legs)
    for leg in legs:
        stamps = [normalize_timestamp(leg.get(key)) for key in ("bid_timestamp", "ask_timestamp")]
        ages = [(now - datetime.fromisoformat(value)).total_seconds() for value in stamps if value]
        bid, ask = leg["bid"], leg["ask"]
        if not contract_identity(leg, symbol, expiration):
            status = "invalid_contract"
        elif identifiers[leg["contract"]] > 1 or strikes[leg["type"], leg["strike"]] > 1:
            status = "ambiguous_contract"
        elif leg.get("outcome") not in (None, "SUCCESS"):
            status = "provider_quote_failure"
        elif bid is None or ask is None or bid < 0 or ask <= 0:
            status = "invalid_price"
        elif bid > ask:
            status = "crossed_market"
        elif len(ages) != 2:
            status = "missing_timestamp"
        elif min(ages) < 0 or any(datetime.fromisoformat(value) > retrieved for value in stamps):
            status = "future_timestamp"
        elif max(ages) > MAX_AGE_SECONDS:
            status = "stale"
        else:
            status = "fresh"
        leg.update(status=status, quote_age_seconds=max(ages) if len(ages) == 2 else None)


def underlying_eligible(bundle, now):
    quote = bundle["quote"]
    stamps = [normalize_timestamp(quote.get(key))
              for key in ("updated_at", "bid_timestamp", "ask_timestamp", "provider_retrieved_at")]
    if any(stamp is None for stamp in stamps):
        return False
    last, bid, ask, retrieved = map(datetime.fromisoformat, stamps)
    return (bundle["freshness"]["market_state"] == "regular_open"
            and quote.get("provider_outcome") == "SUCCESS"
            and bundle["freshness"]["quote_quality"]["bid_ask_valid"]
            and max(last, bid, ask) <= retrieved <= now
            and (now - min(last, bid, ask)).total_seconds() < UNDERLYING_MAX_AGE_SECONDS)


def scenario(chain, buy, sell, spot):
    legs = chain["calls"] + chain["puts"]
    selected = []
    for contract, quantity in ((buy, 1), (sell, -1)):
        if contract is None:
            continue
        matches = [leg for leg in legs if leg["contract"] == contract]
        if len(matches) != 1 or matches[0]["status"] != "fresh":
            return dict(status="unavailable", reason="Selected contract has insufficient pricing evidence.")
        leg = matches[0]
        price = leg["ask"] if quantity > 0 else leg["bid"]
        if price <= 0:
            return dict(status="unavailable", reason="Selected entry price must be positive.")
        selected.append(dict(contract=contract, strike=leg["strike"], type=leg["type"], qty=quantity, price=price))

    credit = -sum(Decimal(str(leg["price"])) * leg["qty"] for leg in selected)
    if len(selected) == 2:
        long, short = selected
        difference = Decimal(str(short["strike"])) - Decimal(str(long["strike"]))
        debit_structure = difference > 0 if long["type"] == "Call" else difference < 0
        if (long["type"] != short["type"] or not difference or not 0 < abs(credit) < abs(difference)
                or (credit < 0) != debit_structure):
            return dict(status="unavailable", reason="Select a same-side vertical with valid conservative pricing.")
    analysis = trade_analysis(dict(spot=spot, shares=0, fees=0, credit=float(credit),
        symbol=chain["symbol"], expiration=chain["expiration"], legs=selected,
        strategy="Vertical" if sell else "Long option", source="Public"), payoff_detail="none")
    return dict(status="available", legs=selected, net_cash=analysis["net_cash"],
        width=analysis["width"], max_loss=analysis["max_loss"],
        max_profit=analysis["max_profit"] if isfinite(analysis["max_profit"]) else None,
        breakevens=analysis["breakevens"])
