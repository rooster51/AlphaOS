"""Authenticated, provider-independent candle endpoint."""
from __future__ import annotations

from typing import Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from modules.data_entitlements import DataUseDenied
from modules.market_data_gateway import MarketDataError
from .contracts import APIError


class CandleBarResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class ProviderEntitlementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    private_research: bool
    public_display: bool
    commercial_use: bool
    redistribution: bool
    ai_analysis: bool
    basis: str
    authorization_reference: str | None = None


class CandleCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    symbols: list[str]
    intervals: list[str]
    sessions: list[str]
    latest_quotes: bool
    native_candles: bool
    provider_native_intervals: bool
    expected_bar_metadata: bool
    entitlement: ProviderEntitlementResponse


class EntitlementDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    use_context: str
    allowed: bool
    code: str
    reason: str
    basis: str
    policy_version: str
    authorization_required: bool
    authorization_reference_present: bool


class CandleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["alphaos-candles-v1"]
    symbol: Literal["SPY", "QQQ"]
    interval: Literal["1m", "5m", "15m"]
    provider: str
    session: Literal["regular"]
    retrieved_at: str
    latest_candle_at: str
    snapshot_id: str
    expected_bars: int | None
    received_bars: int
    returned_bars: int
    completeness: Literal["complete", "incomplete", "unknown"]
    last_bar_status: Literal["complete", "partial", "unknown"]
    freshness: Literal["fresh", "stale", "latest_available", "unknown"]
    warnings: list[str]
    candles: list[CandleBarResponse]
    provider_capabilities: CandleCapabilitiesResponse
    entitlement: EntitlementDecisionResponse


def register_candles(router, service, respond):
    @router.get(
        "/candles/{symbol}",
        response_model=CandleResponse,
        operation_id="get_candles",
        responses={400: {"description": "Unsupported symbol"},
                   403: {"description": "Data use is not entitled"},
                   429: {"description": "Provider throttled the request"},
                   503: {"description": "Provider unavailable"},
                   504: {"description": "Provider timed out"}},
    )
    def candles(
        symbol: str,
        interval: Literal["1m", "5m", "15m"] = "1m",
        session: Literal["regular"] = "regular",
        limit: int = Query(390, ge=1, le=390),
    ):
        try:
            snapshot = service().get(symbol, interval, session, limit)
        except DataUseDenied:
            # Never expose provider details or the underlying decision reason.
            raise APIError("data_use_denied", 403) from None
        except MarketDataError as exc:
            raise APIError(exc.code, exc.status) from None
        return respond(snapshot.as_dict())
