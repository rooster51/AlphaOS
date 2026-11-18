"""Authenticated read-only projection for verified trade intelligence."""
from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import BoundedSemaphore

from fastapi import Query

from modules.data_entitlements import OWNER_PRIVATE_DISPLAY, DataUseDenied, check_data_use
from modules.market_data_gateway import MarketDataError
from modules.price_structure import nearest_levels
from modules.research_control import cancellable_research, checkpoint
from modules.research_timing import emit, execution, stage
from modules.trade_intelligence import build_trade_intelligence
from modules.time_closed_candles import TimeClosedResearch, time_closed_research
from .contracts import APIError
from .service import symbol_value


# Leave time for the website's existing 3.5-second request deadline.
TRADE_INTELLIGENCE_BUDGET_SECONDS = 3.0
TRADE_INTELLIGENCE_WORKERS = 2


def register_trade_intelligence(router, service, candles, respond):
    pool = ThreadPoolExecutor(max_workers=TRADE_INTELLIGENCE_WORKERS, thread_name_prefix="trade-intelligence")
    available = BoundedSemaphore(TRADE_INTELLIGENCE_WORKERS)

    @router.get(
        "/research/trade-intelligence/{symbol}",
        operation_id="get_trade_intelligence",
        responses={
            400: {"description": "Unsupported symbol"},
            409: {"description": "Snapshot does not match the requested symbol/horizon"},
            410: {"description": "Snapshot has expired"},
            503: {"description": "Validated market history is unavailable or research capacity is exhausted"},
            504: {"description": "Trade-intelligence request exceeded its processing deadline"},
        },
    )
    async def trade_intelligence(
        symbol: str,
        horizon: int = 3,
        levels: int = Query(5, ge=1, le=10),
        snapshot_id: str | None = None,
    ):
        normalized = symbol_value(symbol)
        if not available.acquire(blocking=False):
            emit("trade_intelligence_admission", "rejected", outcome="busy")
            raise APIError("trade_intelligence_busy", 503)

        with cancellable_research() as cancelled:
            try:
                work = pool.submit(copy_context().run, calculate, normalized, horizon, levels, snapshot_id)
            except BaseException:
                available.release()
                raise
            # A timed-out network call can still be running. Keep its slot
            # reserved until it exits, so stalled calls cannot build a queue.
            work.add_done_callback(lambda _: available.release())
            try:
                return await asyncio.wait_for(
                    asyncio.wrap_future(work), timeout=TRADE_INTELLIGENCE_BUDGET_SECONDS)
            except TimeoutError:
                emit("trade_intelligence_deadline", "exceeded", outcome="timeout")
                raise APIError("trade_intelligence_timeout", 504) from None
            finally:
                cancelled.set()

    def calculate(normalized, horizon, levels, snapshot_id):
        with execution(normalized, "current"):
            return build_response(normalized, horizon, levels, snapshot_id)

    def build_response(normalized, horizon, levels, snapshot_id):
        research = service()
        # Reuse the market/structure snapshot when the bridge supplies one. The
        # existing service enforces expiry and symbol/horizon consistency.
        with stage("trade_research_snapshot"):
            bundle = research.snapshot(normalized, horizon, snapshot_id=snapshot_id)
        with stage("trade_structure_projection"):
            prepared = bundle["prepared"]
            daily = prepared["dataset"]["features"].tail(2).to_dict("records")
            structure_rows = nearest_levels(prepared["structure"], levels).to_dict("records")

        candle_snapshot = None
        provisional = None
        candle_error = None
        use_time_closed = os.getenv("ALPHAOS_TIME_CLOSED_RESEARCH", "").strip().lower() in ("1", "true", "yes")
        candle_service = candles()
        try:
            checkpoint()
            with stage("trade_5m_candles"):
                first_fetch = candle_service.get_fresh if use_time_closed else candle_service.get
                candle_snapshot = first_fetch(normalized, "5m", "regular", 78)
            if use_time_closed:
                checkpoint()
                with stage("trade_time_closed_refetch"):
                    refetch_started_at = research.clock()
                    refreshed = candle_service.get_fresh(normalized, "5m", "regular", 78)
                    provisional = time_closed_research(
                        candle_snapshot, refreshed, now=research.clock(), enabled=True,
                        refetch_started_at=refetch_started_at,
                    )
        except (MarketDataError, DataUseDenied) as error:
            reason = error.code if isinstance(error, MarketDataError) else "data_use_denied"
            if candle_snapshot is None:
                candle_error = reason
            if use_time_closed:
                provisional = TimeClosedResearch((), "time_closed_unverified_finality", reason)

        checkpoint()
        try:
            with stage("trade_intelligence_calculation"):
                result = build_trade_intelligence(
                    symbol=normalized,
                    now=research.clock(),
                    daily_bars=daily,
                    intraday_snapshot=candle_snapshot,
                    atr=prepared["structure"]["atr"],
                    structure_levels=structure_rows,
                )
        except (ValueError, KeyError, TypeError):
            raise APIError("insufficient_historical_data", 503) from None
        if provisional is not None:
            # Deliberately separate from verified levels, setup state, and
            # options exits. This section is never an actionable signal.
            result["provisional_research"] = {
                "evidence": provisional.evidence,
                "reason": provisional.reason,
                "actionable": False,
                "bar_count": len(provisional.bars),
                "provider": refreshed.provider if provisional.bars else None,
                "owner_private_display_allowed": not provisional.bars or check_data_use(
                    OWNER_PRIVATE_DISPLAY, refreshed.provider,
                ).allowed,
                "observations_at": (
                    [candle_snapshot.retrieved_at, refreshed.retrieved_at] if provisional.bars else []
                ),
                "latest_bar_at": provisional.bars[-1].time if provisional.bars else None,
                "opening_range": provisional.opening_range,
                "vwap": provisional.vwap,
                "ema9": provisional.ema9,
                "directional_context": provisional.directional_context,
                "warning": (
                    "Time-closed candles have not been attested final by the provider. "
                    "Provisional values are not verified BUY/SELL signals."
                ),
            }
            if provisional.bars:
                result["warnings"].append(
                    "Provisional time-closed VWAP/EMA9/opening-range are research-only; "
                    "verified signal state remains independently gated."
                )
        if candle_error:
            result["warnings"].append(
                "The validated intraday candle request failed; only completed daily "
                "session levels are shown and all setups remain WAIT."
            )
        with stage("trade_response_envelope"):
            envelope = research.envelope(result, bundle)
        return respond(envelope)
