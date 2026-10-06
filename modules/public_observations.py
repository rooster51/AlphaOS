"""Public observation snapshots for AlphaOS 2.0 research sessions.

Provider access stays separate from interpretation. This layer fetches/normalizes
observations, records provenance/freshness, and fails closed on stale context.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite

from modules.public_data import get_public_option_chain, get_public_quotes


def _dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _iso(value):
    parsed = _dt(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else None


def _latest_timestamp(row):
    stamps = [_dt(row.get(key)) for key in ("quote_timestamp", "bid_timestamp", "ask_timestamp")]
    stamps = [stamp for stamp in stamps if stamp is not None]
    return min(stamps) if stamps else None


def normalize_public_observations(symbol, expiration, quote, chain, *, observed_at,
                                  max_quote_age_seconds=120):
    """Normalize one Public quote/chain snapshot and validate observation age."""
    symbol = str(symbol).strip().upper()
    now = _dt(observed_at)
    if not symbol or now is None:
        raise ValueError("Symbol and timezone-aware research timestamp required.")
    try:
        max_age = float(max_quote_age_seconds)
    except (TypeError, ValueError):
        raise ValueError("Freshness threshold must be numeric.") from None
    if not isfinite(max_age) or max_age < 0:
        raise ValueError("Freshness threshold must be nonnegative.")
    if not isinstance(quote, dict) or not isinstance(chain, dict):
        raise ValueError("Public quote and chain mappings required.")
    if str(quote.get("symbol", "")).upper() != symbol:
        raise ValueError("Public underlying quote symbol mismatch.")
    if str(chain.get("symbol", "")).upper() != symbol or str(chain.get("expiration")) != str(expiration):
        raise ValueError("Public option-chain context mismatch.")

    underlying_ts = _dt(quote.get("updated_at"))
    spot = quote.get("last")
    issues = []
    if spot is None:
        issues.append("missing_underlying_last")
    if underlying_ts is None:
        issues.append("missing_underlying_timestamp")
    elif (now - underlying_ts).total_seconds() > max_age:
        issues.append("stale_underlying_quote")
    elif underlying_ts > now:
        issues.append("future_underlying_timestamp")

    normalized_chain = {"symbol": symbol, "expiration": str(expiration), "calls": [], "puts": []}
    contract_times = []
    missing_contract_timestamps = 0
    future_contract_timestamps = 0
    stale_contracts = 0
    for pool in ("calls", "puts"):
        rows = chain.get(pool) or []
        if not isinstance(rows, list):
            raise ValueError("Public option-chain pools must be lists.")
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            row = deepcopy(raw)
            row["symbol"] = symbol
            row["expiration"] = str(expiration)
            stamp = _latest_timestamp(row)
            row["quote_timestamp"] = _iso(stamp)
            if stamp is None:
                missing_contract_timestamps += 1
            else:
                contract_times.append(stamp)
                age = (now - stamp).total_seconds()
                if any(_dt(row.get(key)) is not None and _dt(row.get(key)) > now
                       for key in ("quote_timestamp", "bid_timestamp", "ask_timestamp")):
                    future_contract_timestamps += 1
                elif age > max_age:
                    stale_contracts += 1
            normalized_chain[pool].append(row)

    if missing_contract_timestamps:
        issues.append("missing_option_quote_timestamps")
    if not contract_times and not missing_contract_timestamps:
        issues.append("missing_option_quote_timestamps")
    if future_contract_timestamps:
        issues.append("future_option_quote_timestamp")
    if stale_contracts:
        issues.append("stale_option_quotes")

    latest_option = max(contract_times) if contract_times else None
    oldest_option = min(contract_times) if contract_times else None
    fresh = not issues
    return {
        "version": "public-observation-v1",
        "provider": "Public",
        "symbol": symbol,
        "expiration": str(expiration),
        "observed_at": _iso(now),
        "market_research": {
            "symbol": symbol,
            "spot": spot,
            "quote": deepcopy(quote),
            "observation": {
                "provider": "Public",
                "underlying_timestamp": _iso(underlying_ts),
                "latest_option_timestamp": _iso(latest_option),
                "oldest_option_timestamp": _iso(oldest_option),
                "max_quote_age_seconds": max_age,
                "fresh": fresh,
                "issues": issues,
                "missing_contract_timestamp_count": missing_contract_timestamps,
                "stale_contract_count": stale_contracts,
            },
        },
        "chain": normalized_chain,
        "fresh": fresh,
        "issues": issues,
    }


def load_public_observations(symbol, expiration, *, observed_at,
                             max_quote_age_seconds=120):
    """Fetch a current Public quote/chain and return a validated snapshot."""
    symbol = str(symbol).strip().upper()
    quotes = get_public_quotes((symbol,))
    quote = next((row for row in quotes if str(row.get("symbol", "")).upper() == symbol), None)
    if quote is None:
        raise ValueError("Public returned no matching underlying quote.")
    chain = get_public_option_chain(symbol, str(expiration))
    return normalize_public_observations(
        symbol, expiration, quote, chain, observed_at=observed_at,
        max_quote_age_seconds=max_quote_age_seconds,
    )


def research_public_opportunities(symbol, expiration, *, observed_at,
                                  opportunity_state=None, expected_move=None,
                                  available_capital=None, objective=None, width=5,
                                  max_quote_age_seconds=120, history=None, session_context=None,
                                  expected_move_horizon=None, late_minutes=60):
    """Load fresh Public observations and feed the provider-free session.

    Stale/missing/future observations return a no-research payload rather than
    entering the opportunity engine as current evidence.
    """
    from modules.opportunity_classifier import aware_time, classify_opportunity, history_evidence, expected_move_context
    from datetime import date
    if aware_time(observed_at) is None:
        raise ValueError("Timezone-aware research timestamp required.")
    date.fromisoformat(str(expiration))
    snapshot = load_public_observations(
        symbol, expiration, observed_at=observed_at,
        max_quote_age_seconds=max_quote_age_seconds,
    )
    if not snapshot["fresh"]:
        return {
            "version": "public-opportunity-session-v1",
            "symbol": snapshot["symbol"],
            "as_of": snapshot["observed_at"],
            "expiration": snapshot["expiration"],
            "status": "stale_or_incomplete_observations",
            "observation": snapshot["market_research"]["observation"],
            "issues": snapshot["issues"],
            "candidates": [],
            "comparison": None,
            "caveats": [
                "AlphaOS did not run strategy research because current Public observations failed freshness validation.",
                "No stale observation is silently treated as current market evidence.",
            ],
        }
    from modules.opportunity_session import research_market_opportunities

    market = deepcopy(snapshot["market_research"])
    evidence = {}
    if opportunity_state is None:
        try:
            if history is None:
                from modules.public_data import get_public_research_bars
                history = get_public_research_bars(snapshot["symbol"], "FIVE_YEARS")
            evidence = history_evidence(history, snapshot["symbol"], observed_at)
        except (ValueError, RuntimeError):
            evidence = {"unavailable": "Completed market history unavailable or invalid."}
        market["opportunity_state"] = classify_opportunity(evidence, observed_at=observed_at,
            expiration=expiration, session=session_context, late_minutes=late_minutes)
    else:
        market["opportunity_state"] = deepcopy(opportunity_state)
    market["classification_evidence"] = evidence
    market["classification_source"] = 'classifier' if opportunity_state is None else 'caller_supplied_legacy'
    context, comparable = expected_move_context(expected_move, expected_move_horizon, observed_at, expiration)
    market["expected_move_evidence"] = context
    market["expected_move"] = comparable
    session = research_market_opportunities(
        snapshot["symbol"], market, snapshot["chain"],
        as_of=snapshot["observed_at"], expiration=snapshot["expiration"],
        available_capital=available_capital, objective=objective, width=width,
    )
    return {
        "version": "public-opportunity-session-v1",
        "provider_observation": snapshot["market_research"]["observation"],
        "research_session": session,
        "status": session["status"],
    }
