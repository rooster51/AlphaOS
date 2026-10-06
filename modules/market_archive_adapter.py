"""Provider-neutral adapter from the persisted options-archive-v1 payload.

This module does not read Supabase or call a market-data provider. It validates
an already-loaded archive payload and converts one expiration into the normalized
market/chain inputs consumed by AlphaOS opportunity research.
"""
from copy import deepcopy
from datetime import date, timezone
from zoneinfo import ZoneInfo

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
    if options.get("snapshot_date") != session or observed_at.astimezone(ZoneInfo('America/New_York')).date().isoformat() != session:
        raise ValueError("Archive session context mismatch.")
    observed_at = observed_at.astimezone(timezone.utc)
    if underlying.get('symbol', symbol) != symbol:
        raise ValueError('Underlying symbol mismatch.')
    if options.get('provider', payload.get('provider')) != payload.get('provider'):
        raise ValueError('Archive provider mismatch.')
    slot = aware_time(payload.get('slot_time'))
    finished_raw = payload.get('collection_finished_at') or options.get('generated_at')
    finished = aware_time(finished_raw)
    if payload.get('slot_time') is not None and (slot is None or slot > observed_at):
        raise ValueError('Invalid archive slot timestamp.')
    if finished_raw is not None and (finished is None or finished < observed_at):
        raise ValueError('Invalid archive finish timestamp.')
    last_observation = finished or observed_at
    spot = _number(underlying.get("last"))
    if spot is None or spot <= 0:
        raise ValueError("Archive underlying price is unavailable.")

    requested = options.get('requested_expirations') or []
    if not isinstance(requested, list):
        raise ValueError('Requested expirations must be a list.')
    requested = [str(x) for x in requested]
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
    excluded = []
    for bucket in ("valid_contracts", "questionable_contracts", "rejected_contracts"):
        values = options.get(bucket) or []
        if not isinstance(values, list):
            raise ValueError("Archive contract buckets must be lists.")
        for row in values:
            if not isinstance(row, dict):
                excluded.append({'contract': None, 'reason': 'malformed_archive_contract', 'bucket': bucket})
            elif row.get('expiration') == expiration:
                if bucket == 'rejected_contracts':
                    excluded.append({'contract': row.get('contract'), 'reason': 'rejected_archive_contract',
                                     'rejection_reasons': deepcopy(row.get('rejection_reasons') or [])})
                else:
                    rows.append((bucket, row))

    chain = {"symbol": symbol, "expiration": expiration, "calls": [], "puts": []}
    failed_expirations = {item.get('expiration') for item in options.get('expiration_failures') or [] if isinstance(item, dict)}
    for bucket, raw in rows:
        kind = raw.get("type")
        pool = "calls" if kind == "call" else "puts" if kind == "put" else None
        times = [raw.get(k) for k in ('bid_timestamp', 'ask_timestamp', 'last_timestamp', 'observed_at') if raw.get(k) is not None]
        bad_time = any(aware_time(t) is None or aware_time(t) > last_observation for t in times)
        if (pool is None or raw.get("rejection_reasons") or raw.get('symbol') != symbol
                or expiration in failed_expirations or bad_time):
            excluded.append({"contract": raw.get("contract"), "reason": "invalid_archive_contract"})
            continue
        row = deepcopy(raw)
        row["type"] = "Call" if kind == "call" else "Put"
        row["symbol"] = symbol
        row["expiration"] = expiration
        # Collection time is not a provider quote timestamp. Keep both explicit.
        quotes = [aware_time(row[k]) for k in ('bid_timestamp', 'ask_timestamp') if row.get(k) is not None]
        row["quote_timestamp"] = min(quotes).isoformat() if quotes else None
        row['observation_timestamp'] = row.get('observed_at')
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
                "slot_time": payload.get('slot_time'),
                "collection_finished_at": payload.get('collection_finished_at'),
                "collection_started_at": options.get('collection_started_at'),
                "options_generated_at": options.get('generated_at'),
                "requests": deepcopy(options.get('requests') or []),
                "quality_warnings": deepcopy(options.get('warnings') or []),
                "provenance": deepcopy(options.get('provenance') or {}),
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
