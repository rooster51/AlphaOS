"""AlphaOS 2.0 opportunity state and unranked strategy routing.

This module deliberately separates observed/classified market evidence from strategy
construction. Missing dimensions remain unknown. Routes are research families worth
investigating, not recommendations, rankings, or orders.
"""
from __future__ import annotations

ALLOWED = {
    "direction": {"bullish", "bearish", "neutral", "unknown"},
    "premium_state": {"rich", "fair", "cheap", "unknown"},
    "movement_state": {
        "range_bound", "directional", "breakout", "large_move_expected",
        "pin_candidate", "unknown",
    },
    "time_state": {"standard", "late_0dte", "unknown"},
    "volatility_state": {"elevated", "normal", "depressed", "unknown"},
}

ROUTE_MATRIX = {
    ("direction", "bullish", "premium_state", "rich"):
        ("put_credit_spread", "bullish_bwb", "call_debit_spread"),
    ("direction", "bullish", "premium_state", "cheap"):
        ("long_call", "call_debit_spread", "bullish_diagonal"),
    ("direction", "bearish", "premium_state", "rich"):
        ("call_credit_spread", "bearish_bwb", "put_debit_spread"),
    ("direction", "bearish", "premium_state", "cheap"):
        ("long_put", "put_debit_spread", "bearish_diagonal"),
    ("movement_state", "range_bound"):
        ("iron_condor", "butterfly", "bwb", "calendar"),
    ("movement_state", "pin_candidate"):
        ("butterfly", "bwb"),
    ("movement_state", "large_move_expected"):
        ("long_straddle", "long_strangle", "directional_debit_spread"),
    ("movement_state", "breakout"):
        ("long_option", "directional_debit_spread", "directional_bwb"),
    ("volatility_state", "elevated"):
        ("credit_structure", "iron_condor", "butterfly"),
    ("volatility_state", "depressed"):
        ("long_premium", "calendar", "diagonal"),
    ("time_state", "late_0dte"):
        ("vertical", "iron_condor", "butterfly", "bwb"),
}


def opportunity_state(*, direction="unknown", premium_state="unknown",
                      movement_state="unknown", time_state="standard",
                      volatility_state="unknown", evidence=None, caveats=None):
    """Validate already-observed/classified dimensions into a stable state envelope.

    Classification thresholds belong in evidence-producing engines. This function
    never turns a missing metric into bullish/bearish, rich/cheap, or elevated/depressed.
    """
    values = {
        "direction": direction,
        "premium_state": premium_state,
        "movement_state": movement_state,
        "time_state": time_state,
        "volatility_state": volatility_state,
    }
    for key, value in values.items():
        if value not in ALLOWED[key]:
            raise ValueError(f"Invalid {key}: {value}")
    evidence = dict(evidence or {})
    caveats = list(caveats or [])
    unknown = [k for k, v in values.items() if v == "unknown"]
    known = len(values) - len(unknown)
    return {
        "version": "opportunity-state-v1",
        **values,
        "evidence": evidence,
        "evidence_sufficiency": {
            "known_dimensions": known,
            "total_dimensions": len(values),
            "unknown_dimensions": unknown,
            "sufficient_for_routing": known > 0,
        },
        "caveats": caveats,
    }


def route_strategies(state):
    """Return overlapping research routes in deterministic, non-ranked order."""
    if not isinstance(state, dict):
        raise ValueError("Opportunity state must be a mapping.")
    for key, allowed in ALLOWED.items():
        if state.get(key) not in allowed:
            raise ValueError(f"Opportunity state has invalid or missing {key}.")

    matched = []
    routes = []
    seen = set()

    def add(route, reason):
        if route not in seen:
            seen.add(route)
            routes.append(route)
        matched.append({"route": route, "reason": reason})

    # Pair rules first because they express the directional/premium thesis jointly.
    for rule, families in ROUTE_MATRIX.items():
        if len(rule) == 4:
            k1, v1, k2, v2 = rule
            if state[k1] == v1 and state[k2] == v2:
                reason = f"{k1}={v1}; {k2}={v2}"
                for family in families:
                    add(family, reason)
        else:
            key, value = rule
            if state[key] == value:
                reason = f"{key}={value}"
                for family in families:
                    add(family, reason)

    # Directional debit spreads remain investigable when direction is known but
    # premium evidence is unavailable. Long premium does not: cheapness must not
    # be silently inferred.
    if state["direction"] == "bullish" and state["premium_state"] == "unknown":
        add("call_debit_spread", "direction=bullish; premium_state=unknown")
    elif state["direction"] == "bearish" and state["premium_state"] == "unknown":
        add("put_debit_spread", "direction=bearish; premium_state=unknown")

    return {
        "version": "strategy-router-v1",
        "routes": routes,
        "matched_evidence": matched,
        "route_order": "deterministic rule order; not a ranking",
        "no_trade_or_insufficient_evidence": not bool(routes),
        "caveats": [
            "Routes identify strategy families worth researching; they are not recommendations.",
            "Overlapping routes are intentional and no winner is selected.",
            "Unknown evidence does not trigger rich/cheap or elevated/depressed routes.",
        ],
    }


def research_routed_structures(state, candidates, **context):
    """Research supplied supported candidates; no construction or winner selection.

    Generic directional routes require observed bullish/bearish direction. Existing
    family routing remains unchanged; missing candidate economics fail closed.
    """
    from modules.structure_research import research_structure
    routing=route_strategies(state)
    allowed=set(routing['routes'])
    if 'vertical' in allowed or 'directional_debit_spread' in allowed:
        if state['direction']=='bullish':allowed.add('call_debit_spread')
        if state['direction']=='bearish':allowed.add('put_debit_spread')
    if 'bwb' in allowed:allowed.update(('bullish_bwb','bearish_bwb'))
    if 'directional_bwb' in allowed:
        if state['direction']=='bullish':allowed.add('bullish_bwb')
        if state['direction']=='bearish':allowed.add('bearish_bwb')
    results=[];excluded=[]
    for index,candidate in enumerate(candidates):
        try:result=research_structure(candidate,**context)
        except ValueError:
            excluded.append(dict(input_index=index,reason='invalid_or_insufficient_candidate'));continue
        if result['strategy_family'] not in allowed:
            excluded.append(dict(input_index=index,reason='family_not_routed'));continue
        results.append(dict(input_index=index,research=result))
    return dict(routing=routing,candidates=results,excluded=excluded,
        no_candidate=not results,candidate_order='supplied input order; not a ranking')
