"""Provider-neutral market-data contracts.

These types are deliberately independent of Public's SDK models. Adapters
normalize provider responses into these structures, and API/UI/research callers
consume only these fields.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

SUPPORTED_SYMBOLS = ("SPY", "QQQ")
SUPPORTED_INTERVALS = ("1m", "5m", "15m")
SUPPORTED_SESSIONS = ("regular",)
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900}
AGGREGATION_BY_INTERVAL = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTES",
    "15m": "FIFTEEN_MINUTES",
}
Interval = Literal["1m", "5m", "15m"]
MarketSession = Literal["regular"]


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    sessions: tuple[str, ...]
    latest_quotes: bool
    native_candles: bool
    provider_native_intervals: bool
    expected_bar_metadata: bool
    entitlement: dict

    def as_dict(self) -> dict:
        value = asdict(self)
        for key in ("symbols", "intervals", "sessions"):
            value[key] = list(value[key])
        return value


@dataclass(frozen=True)
class CandleBar:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CandleBatch:
    provider: str
    symbol: str
    interval: str
    session: str
    retrieved_at: str
    bars: tuple[CandleBar, ...]
    expected_bars: int | None
    received_bars: int
    last_bar_complete: bool | None
    warnings: tuple[str, ...]
    capabilities: ProviderCapabilities


@dataclass(frozen=True)
class QuoteObservation:
    provider: str
    symbol: str
    last: float
    bid: float | None
    ask: float | None
    previous_close: float | None
    change: float | None
    change_pct: float | None
    volume: float | None
    quote_time: str | None
    retrieved_at: str
    session: str
    market_state: str
    freshness: str
    freshness_reason: str
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        value = asdict(self)
        value["warnings"] = list(value["warnings"])
        return value


@dataclass(frozen=True)
class CandleSnapshot:
    schema_version: str
    symbol: str
    interval: str
    provider: str
    session: str
    retrieved_at: str
    latest_candle_at: str | None
    snapshot_id: str
    expected_bars: int | None
    received_bars: int
    returned_bars: int
    completeness: str
    last_bar_status: str
    freshness: str
    warnings: tuple[str, ...]
    candles: tuple[CandleBar, ...]
    provider_capabilities: dict
    entitlement: dict

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "interval": self.interval,
            "provider": self.provider,
            "session": self.session,
            "retrieved_at": self.retrieved_at,
            "latest_candle_at": self.latest_candle_at,
            "snapshot_id": self.snapshot_id,
            "expected_bars": self.expected_bars,
            "received_bars": self.received_bars,
            "returned_bars": self.returned_bars,
            "completeness": self.completeness,
            "last_bar_status": self.last_bar_status,
            "freshness": self.freshness,
            "warnings": list(self.warnings),
            "candles": [bar.as_dict() for bar in self.candles],
            "provider_capabilities": self.provider_capabilities,
            "entitlement": self.entitlement,
        }
