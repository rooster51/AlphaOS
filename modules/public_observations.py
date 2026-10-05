"""Public observation snapshots for AlphaOS 2.0 research sessions.

Provider access stays separate from interpretation. This layer fetches/normalizes
observations, records provenance/freshness, and fails closed on stale context.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

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
    return max(stamps) if stamps else None


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
    if max_age < 0:
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
                if age < 0:
                    future_contract_timestamps += 1
                elif age > max_age:
                    stale_contracts += 1
            normalized_chain[pool].append(row)

    if not contract_times:
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
