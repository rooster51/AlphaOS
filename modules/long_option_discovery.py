"""Unranked outright-option discovery from a normalized option chain.

The chain shape matches modules.public_data.get_public_option_chain. Discovery
is deterministic and provider-agnostic after normalization: Public supplies
market observations; AlphaOS supplies research context. Candidate order is not
a recommendation or ranking.
"""
from __future__ import annotations

from math import isfinite

from modules.long_option_research import research_long_option


def _number(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _candidate(contract, symbol, expiration, spot, expected_move, as_of):
    kind = str(contract.get("type", "")).title()
    strike = _number(contract.get("strike"))
    ask = _number(contract.get("ask"))
    bid = _number(contract.get("bid"))
    if kind not in ("Call", "Put") or strike is None or ask is None or ask <= 0:
        return None
    research = research_long_option(
        symbol, expiration, kind, strike, ask, spot,
        expected_move=expected_move, as_of=as_of, source="Public option chain",
    )
    spread = ask - bid if bid is not None and bid >= 0 and ask >= bid else None
    mid = _number(contract.get("mid"))
    if mid is None and bid is not None:
        mid = (bid + ask) / 2
    return {
        "candidate_id": f"{symbol}:{expiration}:{kind.lower()}:{strike:g}",
        "symbol": symbol,
        "expiration": expiration,
        "option_type": kind.lower(),
        "contract": contract.get("contract"),
        "strike": strike,
        "entry_assumption": "ask",
        "entry_premium": ask,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "bid_ask_spread": spread,
        "bid_ask_spread_pct_of_mid": (
            spread / mid if spread is not None and mid and mid > 0 else None
        ),
        "delta": _number(contract.get("delta")),
        "gamma": _number(contract.get("gamma")),
        "theta": _number(contract.get("theta")),
        "vega": _number(contract.get("vega")),
        "rho": _number(contract.get("rho")),
        "iv": _number(contract.get("iv")),
        "volume": contract.get("volume"),
        "open_interest": contract.get("open_interest"),
        "research": research,
    }


def discover_long_options(chain, spot, expected_move=None, as_of=None,
                          option_types=("Call", "Put"), max_distance_pct=.05,
                          max_premium=None, min_open_interest=None):
    """Build an unranked set of long-call/put candidates from observed quotes.

    Filters are eligibility constraints only. No score, winner, or preferred
    contract is produced. Natural entry assumes paying the displayed ask.
    """
    spot = _number(spot)
    if spot is None or spot <= 0:
        raise ValueError("Spot must be a positive finite price.")
    if not isinstance(chain, dict) or not chain.get("expiration"):
        raise ValueError("A normalized option chain with expiration is required.")
    symbol = str(chain.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("Option chain symbol is required.")
    allowed = {str(x).title() for x in option_types}
    if not allowed or not allowed <= {"Call", "Put"}:
        raise ValueError("option_types may contain only Call and Put.")
    max_distance_pct = _number(max_distance_pct)
    if max_distance_pct is None or max_distance_pct < 0:
        raise ValueError("max_distance_pct must be nonnegative.")
    if max_premium is not None:
        max_premium = _number(max_premium)
        if max_premium is None or max_premium <= 0:
            raise ValueError("max_premium must be positive.")
    if min_open_interest is not None:
        min_open_interest = int(min_open_interest)
        if min_open_interest < 0:
            raise ValueError("min_open_interest must be nonnegative.")

    rows = []
    pools = []
    if "Call" in allowed:
        pools.extend(chain.get("calls") or [])
    if "Put" in allowed:
        pools.extend(chain.get("puts") or [])
    for contract in pools:
        strike = _number(contract.get("strike"))
        ask = _number(contract.get("ask"))
        if strike is None or ask is None or ask <= 0:
            continue
        if abs(strike / spot - 1) > max_distance_pct + 1e-12:
            continue
        if max_premium is not None and ask > max_premium:
            continue
        if min_open_interest is not None:
            oi = _number(contract.get("open_interest"))
            if oi is None or oi < min_open_interest:
                continue
        row = _candidate(contract, symbol, str(chain["expiration"])[:10], spot,
                         expected_move, as_of)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: (r["option_type"], abs(r["strike"] - spot), r["strike"]))
    return {
        "version": "long-option-discovery-v1",
        "provider": "Public",
        "symbol": symbol,
        "expiration": str(chain["expiration"])[:10],
        "spot": spot,
        "candidate_order": "deterministic proximity order; not a ranking",
        "entry_pricing": "natural ask; displayed quote is not a verified fill",
        "filters": {
            "option_types": sorted(allowed),
            "max_distance_pct": max_distance_pct,
            "max_premium": max_premium,
            "min_open_interest": min_open_interest,
        },
        "candidates": rows,
        "caveats": [
            "Candidate inclusion is not a recommendation.",
            "Public provides observed market data; AlphaOS computes research context.",
            "Greeks and IV are provider observations and may be unavailable for some contracts.",
            "Ask-based economics are research assumptions, not guaranteed execution prices.",
        ],
    }
