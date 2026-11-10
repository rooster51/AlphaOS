"""Synthetic Phase B candle API tests; no Public network calls or credentials."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import alphaos_api.app as api
from modules.candle_service import CandleService
from modules.data_entitlements import PUBLIC_DISPLAY, PRIVATE_RESEARCH, DataUseDenied
from modules.market_data_contracts import (
    INTERVAL_SECONDS,
    SUPPORTED_INTERVALS,
    SUPPORTED_SYMBOLS,
    CandleBar,
    CandleBatch,
)
from modules.market_data_gateway import PUBLIC_CAPABILITIES, MarketDataError

NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
TOKEN = "test-api-secret"


def bars_for(interval: str, count: int = 5) -> tuple[CandleBar, ...]:
    step = INTERVAL_SECONDS[interval]
    end = NOW - timedelta(seconds=step)
    bars = []
    for index in range(count):
        stamp = end - timedelta(seconds=step * (count - 1 - index))
        price = 600.0 + index / 10
        bars.append(CandleBar(
            time=stamp.isoformat(), open=price, high=price + 0.5,
            low=price - 0.5, close=price + 0.2, volume=10_000.0 + index,
        ))
    return tuple(bars)


class FakeProvider:
    """A replacement implementation of the provider protocol."""

    name = "Public"
    capabilities = PUBLIC_CAPABILITIES

    def __init__(self, *, expected: int | None = 5, last_bar_complete: bool | None = True,
                 warnings: tuple[str, ...] = (), error: MarketDataError | None = None):
        self.expected = expected
        self.last_bar_complete = last_bar_complete
        self.warnings = warnings
        self.error = error
        self.calls: list[tuple] = []

    def candles(self, symbol: str, interval: str, session: str = "regular", limit: int = 390):
        self.calls.append((symbol, interval, session, limit))
        if self.error is not None:
            raise self.error
        if str(symbol).upper() not in SUPPORTED_SYMBOLS:
            raise MarketDataError("unsupported_symbol", 400)
        if interval not in SUPPORTED_INTERVALS:
            raise MarketDataError("unsupported_interval", 400)
        all_bars = bars_for(interval)
        bars = all_bars[-min(limit, len(all_bars)):]
        return CandleBatch(
            provider=self.name, symbol=symbol.upper(), interval=interval,
            session=session, retrieved_at=NOW.isoformat(), bars=bars,
            expected_bars=self.expected, received_bars=len(all_bars),
            last_bar_complete=self.last_bar_complete,
            warnings=self.warnings, capabilities=self.capabilities,
        )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ALPHAOS_API_TOKEN", TOKEN)
    return TestClient(api.app)


def install(monkeypatch, service):
    monkeypatch.setitem(api.app.state._state, "candles", service)


def get(client, path="/v1/candles/SPY", **kwargs):
    return client.get(path, headers={"Authorization": f"Bearer {TOKEN}"}, **kwargs)


def test_all_symbols_and_native_intervals_use_normalized_contract():
    for symbol in SUPPORTED_SYMBOLS:
        for interval in SUPPORTED_INTERVALS:
            provider = FakeProvider()
            snapshot = CandleService(provider=provider, clock=lambda: NOW).get(symbol, interval)
            assert snapshot.symbol == symbol
            assert snapshot.interval == interval
            assert snapshot.provider == "Public"
            assert snapshot.returned_bars == snapshot.received_bars == 5
            assert snapshot.completeness == "complete"
            assert snapshot.freshness == "fresh"
            assert snapshot.last_bar_status == "complete"
            assert len(snapshot.candles) == 5
            assert snapshot.provider_capabilities["native_candles"] is True
            assert provider.calls == [(symbol, interval, "regular", 390)]


def test_cache_reuses_snapshot_identity_and_rechecks_entitlement():
    provider = FakeProvider()
    service = CandleService(provider=provider, clock=lambda: NOW)
    first = service.get("SPY", "1m")
    second = service.get("spy", "1m")
    assert first.snapshot_id == second.snapshot_id
    assert provider.calls == [("SPY", "1m", "regular", 390)]

    with pytest.raises(DataUseDenied):
        service.get("SPY", "1m", use_context=PUBLIC_DISPLAY)
    assert provider.calls == [("SPY", "1m", "regular", 390)]
    with pytest.raises(DataUseDenied):
        service.cache.get(("Public", "SPY", "1m", "regular", 390), PUBLIC_DISPLAY)


def test_cache_expires_at_the_bounded_ttl():
    current = [NOW]
    provider = FakeProvider()
    service = CandleService(provider=provider, clock=lambda: current[0])
    service.get("SPY", "1m")
    current[0] = NOW + timedelta(seconds=21)
    service.get("SPY", "1m")
    assert len(provider.calls) == 2


def test_api_requires_authentication(client, monkeypatch):
    install(monkeypatch, CandleService(provider=FakeProvider(), clock=lambda: NOW))
    assert client.get("/v1/candles/SPY").status_code == 401
    assert client.get("/v1/candles/SPY", headers={"Authorization": "Bearer wrong"}).status_code == 403


def test_api_returns_typed_snapshot(client, monkeypatch):
    install(monkeypatch, CandleService(provider=FakeProvider(), clock=lambda: NOW))
    response = get(client, params={"interval": "5m", "session": "regular", "limit": 390})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "alphaos-candles-v1"
    assert payload["symbol"] == "SPY"
    assert payload["interval"] == "5m"
    assert payload["provider"] == "Public"
    assert payload["session"] == "regular"
    assert payload["snapshot_id"]
    assert payload["latest_candle_at"] == bars_for("5m")[-1].time
    assert payload["expected_bars"] == payload["received_bars"] == payload["returned_bars"] == 5
    assert payload["completeness"] == "complete"
    assert payload["last_bar_status"] == "complete"
    assert payload["freshness"] == "fresh"
    assert payload["warnings"] == []
    assert payload["candles"][0]["time"].endswith("+00:00")
    assert payload["provider_capabilities"]["provider"] == "Public"
    assert payload["entitlement"]["use_context"] == PRIVATE_RESEARCH
    assert payload["entitlement"]["allowed"] is True
    assert "account_id" not in response.text


def test_limit_narrows_returned_bars_not_provider_counts(client, monkeypatch):
    install(monkeypatch, CandleService(provider=FakeProvider(), clock=lambda: NOW))
    response = get(client, params={"limit": 2})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["returned_bars"] == 2
    assert payload["received_bars"] == 5
    assert payload["expected_bars"] == 5
    assert payload["completeness"] == "complete"
    assert len(payload["candles"]) == 2


def test_stale_incomplete_and_partial_states_are_explicit(client, monkeypatch):
    provider = FakeProvider(expected=7, last_bar_complete=False)
    service = CandleService(provider=provider, clock=lambda: NOW + timedelta(minutes=5))
    install(monkeypatch, service)
    response = get(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["completeness"] == "incomplete"
    assert payload["last_bar_status"] == "partial"
    assert payload["freshness"] == "stale"
    assert "incomplete_session" in payload["warnings"]
    assert "stale_candles" in payload["warnings"]


def test_http_snapshot_identity_is_stable_across_cache_hit(client, monkeypatch):
    provider = FakeProvider()
    install(monkeypatch, CandleService(provider=provider, clock=lambda: NOW))
    first = get(client)
    second = get(client)
    assert first.status_code == second.status_code == 200
    assert first.json()["snapshot_id"] == second.json()["snapshot_id"]
    assert len(provider.calls) == 1


@pytest.mark.parametrize("path,params,status", [
    ("/v1/candles/IWM", {}, 400),
    ("/v1/candles/SPY", {"interval": "30m"}, 422),
    ("/v1/candles/SPY", {"session": "extended"}, 422),
    ("/v1/candles/SPY", {"limit": 0}, 422),
    ("/v1/candles/SPY", {"limit": 391}, 422),
])
def test_invalid_requests_fail_without_provider_calls(client, monkeypatch, path, params, status):
    provider = FakeProvider()
    install(monkeypatch, CandleService(provider=provider, clock=lambda: NOW))
    response = get(client, path=path, params=params)
    assert response.status_code == status
    assert provider.calls == []


@pytest.mark.parametrize("error,status", [
    (MarketDataError("provider_timeout", 504), 504),
    (MarketDataError("public_rate_limit", 429), 429),
    (MarketDataError("no_candles", 503), 503),
])
def test_provider_failures_are_safe_and_mapped(client, monkeypatch, error, status):
    install(monkeypatch, CandleService(provider=FakeProvider(error=error), clock=lambda: NOW))
    response = get(client)
    assert response.status_code == status
    assert response.json()["error"]["code"] == error.code
    assert "synthetic" not in response.text.lower()


def test_cache_rejects_ttl_outside_the_bounded_window():
    from modules.candle_service import CandleSnapshotCache
    with pytest.raises(ValueError):
        CandleSnapshotCache(lambda: NOW, ttl_seconds=14)
    with pytest.raises(ValueError):
        CandleSnapshotCache(lambda: NOW, ttl_seconds=31)
