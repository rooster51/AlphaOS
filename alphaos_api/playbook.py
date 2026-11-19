"""Owner website bridge entry point for observing the market playbook."""
import os
import sqlite3
from datetime import datetime, timezone
from typing import Literal

from fastapi import Header
from httpx import HTTPError

from modules.data_entitlements import (
    OWNER_PRIVATE_DISPLAY, PRIVATE_RESEARCH, DataUseDenied, enforce_data_use,
)
from modules.market_data_gateway import MarketDataError
from modules.market_playbook import VERSION, PriorSession, evaluate, session_windows
from modules.market_playbook_store import PlaybookJournal
from modules.market_playbook_hosted import MarketPlaybookStorageError, SupabasePlaybookJournal
from modules.supabase_archive import ArchiveUnavailable, research_archive_client
from .contracts import APIError


def _prior_session(research, symbol, provider, windows):
    if provider != "Public" or len(windows) < 2:
        return None
    expected = windows[-2][0].date().isoformat()
    try:
        features = research().completed_history(symbol)["features"]
        for row in features.tail(3).to_dict("records"):
            if str(row["date"])[:10] == expected:
                return PriorSession(
                    symbol, expected, provider, datetime.now(timezone.utc).isoformat(),
                    float(row["high"]), float(row["low"]), float(row["close"]),
                )
    except (APIError, AttributeError, KeyError, TypeError, ValueError):
        return None
    return None


def register_playbook(router, service, research, respond):
    @router.post("/market-playbook/{symbol}", include_in_schema=False)
    def observe(
        symbol: Literal["SPY", "QQQ"],
        data_use: str | None = Header(default=None, alias="X-AlphaOS-Data-Use"),
    ):
        if data_use != OWNER_PRIVATE_DISPLAY:
            raise APIError("data_use_denied", 403)
        database = os.environ.get("ALPHAOS_PLAYBOOK_DB")
        hosted = os.environ.get("ALPHAOS_PLAYBOOK_JOURNAL") == "supabase"
        if not (database or hosted):
            raise APIError("playbook_disabled", 503)

        candles = service()
        provider = candles.provider.name
        try:
            enforce_data_use(PRIVATE_RESEARCH, provider)
            enforce_data_use(OWNER_PRIVATE_DISPLAY, provider)
            try:
                snapshot = candles.get(symbol, "5m", limit=390, use_context=OWNER_PRIVATE_DISPLAY)
            except MarketDataError:
                snapshot = None
            now = datetime.now(timezone.utc)
            if snapshot:
                enforce_data_use(PRIVATE_RESEARCH, snapshot.provider)
                enforce_data_use(OWNER_PRIVATE_DISPLAY, snapshot.provider)
                if snapshot.provider != provider:
                    raise APIError("playbook_provider_mismatch", 503)
                daily = _prior_session(research, symbol, provider, session_windows(now))
                now = datetime.now(timezone.utc)
                view, proposals, bars = evaluate(snapshot, now, daily)
            else:
                windows = session_windows(now)
                view = {
                    "version": VERSION, "symbol": symbol,
                    "session": windows[-1][0].date().isoformat() if windows else None,
                    "provider": provider, "as_of": None, "levels": [], "vwap": None,
                    "provisional_range": None, "structure": "No verified intraday structure.",
                    "bias": "Undetermined", "quality": "Insufficient",
                    "status": "INSUFFICIENT DATA",
                    "reason": "The candle provider is unavailable. Waiting for fresh, confirmed five-minute evidence.",
                    "coverage": {},
                }
                proposals, bars = [], []
            journal = (
                SupabasePlaybookJournal(research_archive_client()) if hosted else PlaybookJournal(database)
            )
            view["history"] = journal.observe(symbol, proposals, bars, now, view.get("provenance"), provider)
        except DataUseDenied:
            raise APIError("data_use_denied", 403) from None
        except (ArchiveUnavailable, HTTPError, MarketPlaybookStorageError, OSError, ValueError, sqlite3.Error):
            raise APIError("playbook_storage_unavailable", 503) from None
        return respond(view)
