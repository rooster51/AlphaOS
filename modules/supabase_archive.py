"""Server-side Supabase persistence for AlphaOS market observations.

Uses the service-role key only in trusted collector infrastructure. Never expose
this key to Streamlit clients, ChatGPT, browser code, logs, or archive payloads.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import urllib.error
import urllib.request


class ArchiveUnavailable(RuntimeError):
    pass


class ArchiveStageError(RuntimeError):
    def __init__(self, stage, exc):
        self.stage = stage
        self.error_type = type(exc).__name__
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        code = getattr(exc, "code", None)
        parts = [f"stage={stage}", f"error={self.error_type}"]
        if status is not None:
            parts.append(f"status={status}")
        if code is not None:
            parts.append(f"code={code}")
        super().__init__("; ".join(parts))


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
    symbol = payload[0]["symbol"]
    aggregation = payload[0]["aggregation"]
    verify = (
        client.table("market_candles")
        .select("id", count="exact")
        .eq("provider", payload[0]["provider"])
        .eq("symbol", symbol)
        .eq("aggregation", aggregation)
        .execute()
    )
    count = getattr(verify, "count", None)
    data = getattr(verify, "data", None)
    if not ((isinstance(count, int) and count > 0) or (isinstance(data, list) and data)):
        raise ArchiveUnavailable(f"Candle persistence verification failed for {symbol}.")
    return len(payload)


def find_slot_snapshot(client, provider, symbol, slot):
    rows = (client.table("option_snapshots").select("id,archive_path,observed_at,quality_status")
            .eq("provider", provider).eq("symbol", symbol).eq("slot_time", slot).execute()).data
    return rows[0] if rows else None


def persist_option_snapshot(client, payload, archive_config=None):
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    compressed = gzip.compress(raw, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    symbol = payload["symbol"]
    observed = payload["observed_at"]
    date = payload["session"]
    stamp = payload.get("slot_time", observed).replace(":", "").replace("-", "")
    path = f"options/symbol={symbol}/date={date}/{stamp}.json.gz"

    # Use Storage's HTTP API directly here. The Python Storage client can mask
    # non-JSON gateway/error responses as JSONDecodeError, which prevents safe
    # diagnosis in unattended collectors.
    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    upload_url = f"{base_url}/storage/v1/object/market-archive/{path}"
    request = urllib.request.Request(
        upload_url,
        data=compressed,
        method="POST",
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/gzip",
            "x-upsert": "false",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if not 200 <= response.status < 300:
                raise ArchiveUnavailable(f"Storage upload returned HTTP {response.status}.")
    except (urllib.error.HTTPError, urllib.error.URLError):
        # An earlier invocation may have committed the immutable object but not
        # its metadata. Recover that exact winner, never overwrite raw evidence.
        try:
            saved = client.storage.from_("market-archive").download(path)
            canonical = json.loads(gzip.decompress(saved))
            if any(canonical.get(k) != payload.get(k) for k in ("provider", "symbol", "session", "slot_time")):
                raise ValueError("Archive identity mismatch")
            payload = canonical
            observed = payload["observed_at"]
            digest = hashlib.sha256(saved).hexdigest()
        except Exception:
            raise ArchiveUnavailable("Storage upload/recovery failed.") from None

    options = payload.get("options")
    if not isinstance(options, dict):
        raise ArchiveUnavailable("Option snapshot payload does not match options-archive-v1.")
    underlying = payload.get("underlying")
    if not isinstance(underlying, dict):
        raise ArchiveUnavailable("Underlying snapshot payload is invalid.")
    row = {
        "provider": payload["provider"],
        "symbol": symbol,
        "observed_at": observed,
        "session_date": date,
        "underlying_price": underlying.get("last"),
        "min_dte": int(archive_config["min_dte"]) if archive_config else None,
        "max_dte": int(archive_config["max_dte"]) if archive_config else None,
        "strike_band": float(archive_config["strike_band"]) if archive_config else None,
        "contract_count": options.get("received_contract_count", 0),
        "archive_path": path,
        "archive_sha256": digest,
        "quality_status": options.get("status"),
    }
    if payload.get("slot_time"):
        row["slot_time"] = payload["slot_time"]
    try:
        client.table("option_snapshots").upsert(row, on_conflict="provider,symbol,observed_at", ignore_duplicates=True).execute()
    except Exception as exc:
        raise ArchiveStageError("option_snapshot_insert", exc) from None
    verify = (
        client.table("option_snapshots")
        .select("id,archive_path,observed_at,quality_status")
        .eq("provider", payload["provider"])
        .eq("symbol", symbol)
        .eq("observed_at", observed)
        .execute()
    )
    verified = getattr(verify, "data", None)
    if not isinstance(verified, list) or not verified:
        raise ArchiveUnavailable(f"Option snapshot persistence verification failed for {symbol}.")
    return verified[0]
