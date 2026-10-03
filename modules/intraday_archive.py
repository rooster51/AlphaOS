"""Point-in-time intraday market archive built on the existing Public provider.

Raw observations are preserved independently of AlphaOS strategy/research output.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.options_archive import build_options_snapshot

NY = ZoneInfo("America/New_York")
VERSION = "intraday-archive-v1"


def _iso_utc(value):
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def normalize_underlying_quote(raw, symbol, observed_at):
    instrument = raw.get("instrument") if isinstance(raw, dict) else None
    if not isinstance(instrument, dict) or instrument.get("symbol") != symbol:
        raise ValueError("underlying quote symbol mismatch")
    return {
        "schema_version": VERSION,
        "provider": "Public",
        "symbol": symbol,
        "observed_at": _iso_utc(observed_at),
        "last": raw.get("last"),
        "bid": raw.get("bid"),
        "ask": raw.get("ask"),
        "volume": raw.get("volume"),
        "previous_close": raw.get("previousClose"),
        "last_timestamp": raw.get("lastTimestamp"),
        "bid_timestamp": raw.get("bidTimestamp"),
        "ask_timestamp": raw.get("askTimestamp"),
    }


def collect_symbol(provider, symbol, config, now=None):
    now = now or provider.now()
    session = now.astimezone(NY).date().isoformat()
    quote = normalize_underlying_quote(provider.underlying(symbol), symbol, now)
    options_config = {
        "min_dte": int(config["min_dte"]),
        "max_dte": int(config["max_dte"]),
        "strike_band": float(config["strike_band"]),
    }
    options = build_options_snapshot(
        provider, symbol, session, options_config,
        config_version=config.get("schema_version", "intraday-archive-config-v1"),
        config_hash="runtime-config",
    )
    return {
        "schema_version": VERSION,
        "provider": provider.name,
        "symbol": symbol,
        "session": session,
        "observed_at": _iso_utc(now),
        "underlying": quote,
        "options": options,
    }


def snapshot_path(root, symbol, observed_at):
    stamp = observed_at.astimezone(NY)
    return Path(root) / "snapshots" / f"symbol={symbol}" / f"date={stamp.date().isoformat()}" / f"{stamp.strftime('%H%M%S')}.json.gz"


def load_config(path="config/intraday_archive.json"):
    return json.loads(Path(path).read_text())
