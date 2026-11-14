"""Authenticated read-only projection for verified trade intelligence."""
from __future__ import annotations

from fastapi import Query

from modules.data_entitlements import DataUseDenied
from modules.market_data_gateway import MarketDataError
from modules.price_structure import nearest_levels
from modules.trade_intelligence import build_trade_intelligence
from .contracts import APIError
from .service import symbol_value


def register_trade_intelligence(router, service, candles, respond):
    @router.get(
        "/research/trade-intelligence/{symbol}",
        operation_id="get_trade_intelligence",
        responses={
            400: {"description": "Unsupported symbol"},
            503: {"description": "Validated market history is unavailable"},
        },
    )
    def trade_intelligence(
        symbol: str,
        horizon: int = 3,
        levels: int = Query(5, ge=1, le=10),
    ):
        try:
            normalized = symbol_value(symbol)
        except APIError:
            raise
        research = service()
        bundle = research.snapshot(normalized, horizon)
        prepared = bundle["prepared"]
        daily = prepared["dataset"]["features"].tail(2).to_dict("records")
        structure_rows = nearest_levels(prepared["structure"], levels).to_dict("records")

        candle_snapshot = None
        candle_error = None
        try:
            candle_snapshot = candles().get(normalized, "5m", "regular", 78)
        except (MarketDataError, DataUseDenied):
            candle_error = "intraday_candles_unavailable"

        try:
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
        if candle_error:
            result["warnings"].append(
                "The validated intraday candle request failed; only completed daily "
                "session levels are shown and all setups remain WAIT."
            )
        return respond(research.envelope(result, bundle))
