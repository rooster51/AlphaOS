"""Identity and pricing gates for the explicitly dated ETF chain."""
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from functools import reduce
from math import gcd, isfinite
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from modules.options_payoff import trade_analysis
from modules.quote_freshness import normalize_timestamp
from modules.structure_research import _family

MAX_AGE_SECONDS = 30
UNDERLYING_MAX_AGE_SECONDS = 15
CONTRACT_MULTIPLIER = 100


class ResearchLeg(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    contract: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z]+ *\d{6}[CP]\d{8}$")
    qty: int = Field(ge=-20, le=20)

    @model_validator(mode="after")
    def nonzero(self):
        if self.qty == 0:
            raise ValueError("Signed quantity must be nonzero.")
        return self


class ResearchScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    strategy: Literal[
        "long_call", "long_put", "call_debit_spread", "put_debit_spread",
        "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly",
        "long_call_butterfly", "long_put_butterfly", "long_straddle", "long_strangle", "custom",
    ]
    legs: list[ResearchLeg] = Field(min_length=1, max_length=8)


class ResearchLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    max_debit: float | None = Field(default=None, ge=0, le=1e9)
    max_loss: float | None = Field(default=None, ge=0, le=1e9)
    min_credit: float = Field(default=0, ge=0, le=1e9)
    max_contracts: int = Field(default=20, ge=1, le=160, strict=True)
    max_bid_ask_spread: float | None = Field(default=None, ge=0, le=10000)
    dte_min: int = Field(default=0, ge=0, le=3650, strict=True)
    dte_max: int = Field(default=3650, ge=0, le=3650, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.dte_min > self.dte_max:
            raise ValueError("DTE range must be ordered.")
        return self


class ChainResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    scenarios: list[ResearchScenario] = Field(min_length=1, max_length=8)
    limits: ResearchLimits = Field(default_factory=ResearchLimits)
    entry_fee_per_contract: float = Field(default=0.65, ge=0, le=100)


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


def strategy_geometry(legs):
    """Reuse the shared structure classifier after normalizing whole position units."""
    scale = reduce(gcd, (abs(leg["qty"]) for leg in legs))
    normalized = [{**leg, "qty": leg["qty"] // scale} for leg in legs]
    if len(normalized) == 1 and normalized[0]["qty"] == 1:
        return ("long_call", "bullish") if normalized[0]["type"] == "Call" else ("long_put", "bearish")
    if len(normalized) == 2 and {leg["type"] for leg in normalized} == {"Call", "Put"}:
        call = next(leg for leg in normalized if leg["type"] == "Call")
        put = next(leg for leg in normalized if leg["type"] == "Put")
        if call["qty"] == put["qty"] == 1 and put["strike"] <= call["strike"]:
            return ("long_straddle" if put["strike"] == call["strike"] else "long_strangle", "two_sided")
    family, direction = _family(normalized)
    if family == "butterfly":
        strikes = sorted(set(Decimal(str(leg["strike"])) for leg in normalized))
        if len(strikes) != 3 or strikes[1] - strikes[0] != strikes[2] - strikes[1]:
            raise ValueError("Butterfly wings must be equal.")
        family = "iron_butterfly" if len(normalized) == 4 else (
            "long_call_butterfly" if normalized[0]["type"] == "Call" else "long_put_butterfly")
    if family in ("bullish_bwb", "bearish_bwb"):
        raise ValueError("Broken wings require custom signed-leg research.")
    return family, direction


def unavailable_scenario(request, reason, **evidence):
    return dict(strategy=request.strategy, status="unavailable", eligible_for_analysis=False,
        reason=reason, **evidence)


def research_scenario(chain, request, spot, now, retrieved_at, limits, entry_fee_per_contract):
    """Price observed contracts; the existing payoff engine owns all economics."""
    from zoneinfo import ZoneInfo
    expiration = chain["expiration"]
    dte = (date.fromisoformat(expiration) - now.astimezone(ZoneInfo("America/New_York")).date()).days
    if dte < 0:
        return unavailable_scenario(request, "expired_contract")
    if len({leg.contract for leg in request.legs}) != len(request.legs):
        return unavailable_scenario(request, "duplicate_contracts")
    rows = chain["calls"] + chain["puts"]
    assess_contracts(rows, chain["symbol"], expiration, now, retrieved_at)
    selected, warnings = [], []
    for selection in request.legs:
        matches = [row for row in rows if row["contract"] == selection.contract]
        if len(matches) != 1 or matches[0]["status"] != "fresh":
            return unavailable_scenario(request, "insufficient_contract_evidence")
        row = matches[0]
        price = row["ask"] if selection.qty > 0 else row["bid"]
        if price <= 0:
            return unavailable_scenario(request, "nonpositive_entry_price")
        selected.append({**row, "qty": selection.qty, "price": price, "expiration": expiration})
        size = row.get("ask_size" if selection.qty > 0 else "bid_size")
        if size is None:
            warnings.append(f"{selection.contract}: displayed entry size unavailable.")
        elif size < abs(selection.qty):
            warnings.append(f"{selection.contract}: displayed entry size below selected quantity.")
        for field in ("volume", "open_interest"):
            if row.get(field) is None or row[field] <= 0:
                warnings.append(f"{selection.contract}: {field.replace('_', ' ')} unavailable or zero.")
    try:
        family, direction = strategy_geometry(selected)
    except ValueError:
        family, direction = "custom", "mixed"
    if request.strategy != "custom" and family != request.strategy:
        return unavailable_scenario(request, "unsupported_strategy_geometry")
    credit = -sum(Decimal(str(leg["price"])) * leg["qty"] for leg in selected)
    debit_families = {"long_call", "long_put", "call_debit_spread", "put_debit_spread",
        "long_call_butterfly", "long_put_butterfly", "long_straddle", "long_strangle"}
    credit_families = {"put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly"}
    if request.strategy != "custom" and (
        (family in debit_families and credit >= 0) or (family in credit_families and credit <= 0)):
        return unavailable_scenario(request, "entry_cashflow_conflicts_with_geometry")
    count = sum(abs(leg["qty"]) for leg in selected)
    fees = float(Decimal(str(entry_fee_per_contract)) * count)
    analysis = trade_analysis(dict(symbol=chain["symbol"], expiration=expiration, spot=spot,
        shares=0, fees=fees, credit=float(credit), legs=selected, strategy=request.strategy,
        source="Public natural entry observations"), payoff_detail="full")
    profit, risk = analysis["max_profit"], analysis["max_loss"]
    if request.strategy != "custom" and (profit <= 0 or not isfinite(risk) or risk <= 0):
        return unavailable_scenario(request, "entry_has_no_positive_risk_reward")
    breaches = []
    debit = max(0, -analysis["net_cash"])
    if limits.max_debit is not None and debit > limits.max_debit:
        breaches.append("maximum_debit_exceeded")
    if limits.max_loss is not None and risk > limits.max_loss:
        breaches.append("maximum_loss_exceeded")
    if credit > 0 and analysis["net_cash"] < limits.min_credit:
        breaches.append("minimum_credit_not_met")
    if count > limits.max_contracts:
        breaches.append("maximum_contracts_exceeded")
    if limits.max_bid_ask_spread is not None and any(
        Decimal(str(leg["ask"])) - Decimal(str(leg["bid"])) > Decimal(str(limits.max_bid_ask_spread))
        for leg in selected):
        breaches.append("maximum_bid_ask_spread_exceeded")
    if not limits.dte_min <= dte <= limits.dte_max:
        breaches.append("dte_outside_range")
    greek_exposure = {}
    for greek in ("delta", "gamma", "theta", "vega", "rho"):
        values = [leg.get(greek) for leg in selected]
        greek_exposure[greek] = sum(value * leg["qty"] * CONTRACT_MULTIPLIER
            for leg, value in zip(selected, values)) if all(
                isinstance(value, (int, float)) and isfinite(value) for value in values) else None
    return dict(strategy=request.strategy, geometry=family, direction=direction,
        status="unavailable" if breaches else "available", eligible_for_analysis=not breaches,
        reason="risk_limits_exceeded" if breaches else None, limit_breaches=breaches,
        symbol=chain["symbol"], expiration=expiration, dte=dte, legs=selected,
        contract_multiplier=CONTRACT_MULTIPLIER, total_contracts=count,
        evaluated_at=now.isoformat(), retrieved_at=retrieved_at,
        oldest_quote_age_seconds=max(leg["quote_age_seconds"] for leg in selected),
        entry_premium=float(credit * CONTRACT_MULTIPLIER), entry_fees=fees,
        net_cash=analysis["net_cash"], entry_debit=debit, entry_credit=max(0, analysis["net_cash"]),
        max_profit=profit if isfinite(profit) else None, profit_unbounded=not isfinite(profit),
        max_loss=risk if isfinite(risk) else None, loss_unbounded=not isfinite(risk),
        capital_at_risk=risk if isfinite(risk) else None,
        return_on_max_risk=analysis["return_on_risk"], breakevens=analysis["breakevens"],
        payoff=[dict(terminal_price=row["Terminal underlying ($)"], pnl=row["Expiration P&L ($)"])
            for row in analysis["grid"]],
        liquidity_warnings=warnings, greek_exposure=greek_exposure,
        capital_treatment="fully_paid_long_options" if all(leg["qty"] > 0 for leg in selected)
            else "complex_margin_and_assignment" if request.strategy == "custom" else "defined_risk_with_assignment",
        assumptions=[
            "Buy at ask and sell at bid; displayed quotes do not guarantee fills.",
            "Entry fees charged once per absolute contract; exit fees and exercise/assignment charges excluded.",
            "Same-expiration standard 100-share contracts; payoff assumes all legs held through expiration.",
            "Theoretical capital at risk does not establish brokerage buying power.",
            "Greeks are provider observations; future volatility and expiration sensitivity may change.",
            "Event risk evidence unavailable. Payoff validity does not establish a trading edge.",
        ])
