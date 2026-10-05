"""Server-side Supabase persistence for AlphaOS market observations.

Uses the service-role key only in trusted collector infrastructure. Never expose
this key to Streamlit clients, ChatGPT, browser code, logs, or archive payloads.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os


class ArchiveUnavailable(RuntimeError):
    pass


def archive_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ArchiveUnavailable(
            "Supabase archive credentials are not configured for the collector."
        )
    from supabase import create_client
    return create_client(url, key)


def persist_candles(client, rows):
    if not rows:
        return 0
    payload = [{
        "provider": r["provider"],
        "symbol": r["symbol"],
        "aggregation": r["aggregation"],
        "bar_time": r["timestamp"],
        "open": r["open"], "high": r["high"], "low": r["low"],
        "close": r["close"], "volume": r.get("volume"),
        "retrieved_at": r["retrieved_at"],
    } for r in rows]
    client.table("market_candles").upsert(
        payload, on_conflict="provider,symbol,aggregation,bar_time"
    ).execute()
    return len(payload)


def persist_option_snapshot(client, payload):
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    compressed = gzip.compress(raw)
    digest = hashlib.sha256(compressed).hexdigest()
    symbol = payload["symbol"]
    observed = payload["observed_at"]
    date = payload["session"]
    stamp = observed.replace(":", "").replace("-", "")
    path = f"options/symbol={symbol}/date={date}/{stamp}.json.gz"

    client.storage.from_("market-archive").upload(
        path, compressed,
        {"content-type": "application/gzip", "upsert": "false"},
    )

    options = payload.get("options") or {}
    observations = options.get("observations") or options.get("contracts") or []
    underlying = payload.get("underlying") or {}
    row = {
        "provider": payload["provider"],
        "symbol": symbol,
        "observed_at": observed,
        "session_date": date,
        "underlying_price": underlying.get("last"),
        "contract_count": len(observations),
        "archive_path": path,
        "archive_sha256": digest,
        "quality_status": options.get("status"),
    }
    result = client.table("option_snapshots").insert(row).execute()
    data = getattr(result, "data", None) or []
    return data[0] if data else row
