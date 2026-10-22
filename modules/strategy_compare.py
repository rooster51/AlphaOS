"""Cross-strategy evidence normalization for AlphaOS 2.0.

Comparison is descriptive only: preserve supplied order, expose common evidence,
and never score, rank, recommend, or choose a winner.
"""
from math import isfinite
from datetime import date

from modules.options_payoff import trade_analysis, validate_trade


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _family(item):
    return (
        item.get("strategy_family")
        or (item.get("trade") or {}).get("strategy_family")
        or (item.get("trade") or {}).get("strategy")
    )


def _infer_long_pair(trade):
    """Recognize only unambiguous native long pairs; never infer an entry price."""
    symbol = trade.get("symbol")
    expiration = trade.get("expiration")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Underlying required for shape recognition.")
    if not isinstance(expiration, str):
        raise ValueError("Expiration required for shape recognition.")
    date.fromisoformat(expiration)
    if trade.get("underlying", symbol) != symbol:
        raise ValueError("Underlying mismatch.")
    if any(_number(trade.get(key)) is None for key in ("spot", "credit", "shares", "fees")):
        raise ValueError("Explicit finite cashflows, fees and position required.")
    legs = trade.get("legs")
    if not isinstance(legs, list) or len(legs) != 2:
        raise ValueError("Exactly two native option legs required.")
    for leg in legs:
        if not isinstance(leg, dict):
            raise ValueError("Invalid leg.")
        if leg.get("symbol", symbol) != symbol or leg.get("underlying", symbol) != symbol:
            raise ValueError("Leg underlying mismatch.")
        if leg.get("expiration", expiration) != expiration:
            raise ValueError("Leg expiration mismatch.")
        qty = _number(leg.get("qty"))
        if _number(leg.get("strike")) is None:
            raise ValueError("Finite strike required.")
        if qty is None or qty <= 0 or not qty.is_integer():
            raise ValueError("Whole positive quantities required.")
        # Native signed qty is authoritative; reject conflicting alternate forms.
        if "action" in leg and leg["action"] != "Buy":
            raise ValueError("Conflicting leg action.")
        if "quantity" in leg and _number(leg["quantity"]) != qty:
            raise ValueError("Conflicting leg quantity.")
    normalized = validate_trade(trade)
    if normalized["shares"] != 0 or normalized["credit"] >= 0:
        raise ValueError("Option-only long pairs require an explicit debit.")
    legs = normalized["legs"]
    if {leg["type"] for leg in legs} != {"Call", "Put"} or legs[0]["qty"] != legs[1]["qty"]:
        raise ValueError("Equal long call and put quantities required.")
    call = next(leg for leg in legs if leg["type"] == "Call")
    put = next(leg for leg in legs if leg["type"] == "Put")
    if put["strike"] > call["strike"]:
        raise ValueError("Inverted long pair is unsupported.")
    family = "long_straddle" if put["strike"] == call["strike"] else "long_strangle"
    return family, normalized


def _breakevens(item):
    roots = item.get("breakevens")
    if roots is None:
        root = item.get("breakeven")
        roots = [] if root is None else [root]
    return [float(x) for x in roots if _number(x) is not None]


def _expected_move(item):
    context = item.get("expected_move_context")
    if not isinstance(context, dict):
        return None
    return _number(context.get("expected_move"))


def normalize_comparison_candidate(item, input_index):
    """Project one researched candidate into shared, non-ranking evidence."""
    if not isinstance(item, dict):
        raise ValueError("Researched candidate must be a mapping.")
    trade = item.get("trade")
    if not isinstance(trade, dict):
        raise ValueError("Researched candidate requires a normalized trade.")
    family = _family(item)
    if not family:
        family, trade = _infer_long_pair(trade)
        analysis = trade_analysis(trade)
        # Ignore cached economics only on this new inference path. Existing
        # explicitly classified researched candidates retain their contract.
        item = dict(item, capital_at_risk=analysis["max_loss"],
                    max_loss=analysis["max_loss"], max_profit=analysis["max_profit"],
                    breakevens=analysis["breakevens"])
    spot = _number(trade.get("spot"))
    risk = _number(item.get("capital_at_risk", item.get("max_loss")))
    if not family or spot is None or spot <= 0 or risk is None or risk < 0:
        raise ValueError("Candidate lacks required comparison economics.")

    max_profit_raw = item.get("max_profit")
    max_profit = _number(max_profit_raw)
    unlimited_profit = max_profit_raw == float("inf")
    roots = _breakevens(item)
    moves = [root - spot for root in roots]
    em = _expected_move(item)

    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    legs = evidence.get("option_legs") if isinstance(evidence.get("option_legs"), list) else []
    observed = {
        key: any(isinstance(leg, dict) and leg.get(key) is not None for leg in legs)
        for key in ("bid", "ask", "delta", "gamma", "theta", "vega", "iv", "volume", "open_interest")
    }

    return {
        "input_index": input_index,
        "strategy_family": family,
        "direction": item.get("direction"),
        "expiration": trade.get("expiration"),
        "dte": item.get("dte"),
        "capital_at_risk": risk,
        "max_loss": _number(item.get("max_loss", risk)),
        "max_profit": "unlimited" if unlimited_profit else max_profit,
        "breakevens": roots,
        "breakeven_moves": moves,
        "breakeven_move_pcts": [move / spot for move in moves],
        "expected_move": em,
        "breakeven_distances_in_expected_moves": (
            [abs(move) / em if em else None for move in moves] if em is not None else None
        ),
        "market_evidence_available": observed,
        "pricing_assumption": evidence.get("pricing_assumption"),
        "caveats": list(item.get("caveats") or []),
    }


def compare_strategy_research(candidates, *, thesis=None):
    """Return common evidence for heterogeneous researched candidates.

    Invalid/insufficient candidates are excluded explicitly. Output order is the
    supplied order and has no attractiveness meaning.
    """
    if not isinstance(candidates, list):
        raise ValueError("Candidates must be supplied as a list.")

    compared, excluded = [], []
    for index, item in enumerate(candidates):
        try:
            compared.append(normalize_comparison_candidate(item, index))
        except (ValueError, TypeError, OverflowError):
            excluded.append({"input_index": index, "reason": "invalid_or_insufficient_research"})

    fields = (
        "capital_at_risk", "max_loss", "max_profit", "breakevens",
        "breakeven_moves", "breakeven_move_pcts", "dte", "expected_move",
        "breakeven_distances_in_expected_moves", "market_evidence_available",
    )
    return {
        "version": "cross-strategy-compare-v1",
        "thesis": thesis,
        "candidates": compared,
        "excluded": excluded,
        "no_candidate": not compared,
        "comparison_fields": list(fields),
        "candidate_order": "supplied input order; not a ranking",
        "winner": None,
        "recommendation": None,
        "caveats": [
            "Comparison is descriptive research, not a score, ranking, or recommendation.",
            "Missing evidence remains unavailable and is not imputed.",
            "Unlimited profit potential is preserved rather than converted into a reward/risk score.",
            "Expected-move context is descriptive and does not imply probability of profit.",
        ],
    }
