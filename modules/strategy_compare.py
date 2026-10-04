"""Cross-strategy evidence normalization for AlphaOS 2.0.

Comparison is descriptive only: preserve supplied order, expose common evidence,
and never score, rank, recommend, or choose a winner.
"""
from math import isfinite


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
