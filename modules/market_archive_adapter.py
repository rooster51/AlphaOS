"""Provider-neutral adapter from the persisted options-archive-v1 payload.

This module does not read Supabase or call a market-data provider. It validates
an already-loaded archive payload and converts one expiration into the normalized
market/chain inputs consumed by AlphaOS opportunity research.
"""
from copy import deepcopy
from datetime import date

from modules.opportunity_classifier import aware_time
from modules.structure_research import _number

VERSION = "market-archive-adapter-v1"


def normalize_archive_snapshot(payload, expiration=None):
    if not isinstance(payload, dict) or payload.get("schema_version") != "intraday-archive-v1":
        raise ValueError("intraday-archive-v1 payload required.")
    symbol = str(payload.get("symbol") or "").strip().upper()
    observed_at = aware_time(payload.get("observed_at"))
    session = str(payload.get("session") or "")
    underlying = payload.get("underlying")
    options = payload.get("options")
    if not symbol or observed_at is None or not isinstance(underlying, dict) or not isinstance(options, dict):
        raise ValueError("Archive symbol, timestamp, underlying and options are required.")
    if options.get("schema_version") != "options-archive-v1" or str(options.get("symbol") or "").upper() != symbol:
        raise ValueError("Options archive context mismatch.")
    if options.get("snapshot_date") != session or observed_at.date().isoformat() != session:
        raise ValueError("Archive session context mismatch.")
    spot = _number(underlying.get("last"))
    if spot is None or spot <= 0:
        raise ValueError("Archive underlying price is unavailable.")

    requested = [str(x) for x in options.get("requested_expirations") or []]
    if expiration is None:
        if not requested:
            raise ValueError("Archive contains no requested expiration.")
        expiration = requested[0]
    expiration = str(expiration)
    try:
        if date.fromisoformat(expiration) < date.fromisoformat(session):
            raise ValueError("Archive expiration precedes session.")
    except ValueError:
        raise ValueError("Valid archive expiration required.") from None
    if expiration not in requested:
        raise ValueError("Expiration was not requested in this archive snapshot.")

    rows = []
    for bucket in ("valid_contracts", "questionable_contracts"):
        values = options.get(bucket) or []
        if not isinstance(values, list):
            raise ValueError("Archive contract buckets must be lists.")
        rows.extend((bucket, row) for row in values if isinstance(row, dict) and row.get("expiration") == expiration)

    chain = {"symbol": symbol, "expiration": expiration, "calls": [], "puts": []}
    excluded = []
    for bucket, raw in rows:
        kind = raw.get("type")
        pool = "calls" if kind == "call" else "puts" if kind == "put" else None
        if pool is None or raw.get("rejection_reasons"):
            excluded.append({"contract": raw.get("contract"), "reason": "invalid_archive_contract"})
            continue
        row = deepcopy(raw)
        row["type"] = "Call" if kind == "call" else "Put"
        row["symbol"] = symbol
        row["expiration"] = expiration
        row["quote_timestamp"] = row.get("bid_timestamp") or row.get("ask_timestamp") or row.get("observed_at")
        row["archive_quality"] = bucket
        chain[pool].append(row)

    return {
        "version": VERSION,
        "provider": payload.get("provider"),
        "symbol": symbol,
        "observed_at": observed_at.isoformat(),
        "session_date": session,
        "expiration": expiration,
        "market_research": {
            "symbol": symbol,
            "spot": spot,
            "archive_observation": {
                "provider": payload.get("provider"),
                "schema_version": payload.get("schema_version"),
                "options_schema_version": options.get("schema_version"),
                "options_status": options.get("status"),
                "quote_timing": options.get("quote_timing"),
                "observed_at": observed_at.isoformat(),
                "underlying_last_timestamp": underlying.get("last_timestamp"),
                "requested_expirations": requested,
                "expiration_failures": deepcopy(options.get("expiration_failures") or []),
            },
        },
        "chain": chain,
        "excluded": excluded,
        "caveats": [
            "Archive observations are point-in-time evidence, not guaranteed executable fills.",
            "Questionable contracts are retained with their archive quality warnings; rejected contracts are not promoted.",
            "No market regime, expected move, ranking or recommendation is inferred by this adapter.",
        ],
    }
