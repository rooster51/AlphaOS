"""Synthetic endpoint tests for the read-only trade-intelligence projection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import alphaos_api.app as api
from modules.data_entitlements import PRIVATE_RESEARCH, check_data_use
from modules.market_data_contracts import CandleBar, CandleBatch
from modules.market_data_gateway import (
    PUBLIC_CAPABILITIES,
    MarketDataError,
    build_snapshot,
)

NOW = datetime(2026, 11, 13, 14, 50, tzinfo=timezone.utc)
OPEN = NOW.replace(hour=14, minute=30)
TOKEN = "trade-intelligence-test-token"


def candles(*closes):
    bars = []
    for index, close in enumerate(closes):
        bars.append(CandleBar(
            time=(OPEN + index * timedelta(minutes=5)).isoformat(),
            open=close - 0.05, high=close + 0.5, low=close - 0.5,
            close=close, volume=1000.0,
        ))
    batch = CandleBatch(
        provider="Public", symbol="SPY", interval="5m", session="regular",
        retrieved_at=NOW.isoformat(), bars=tuple(bars), expected_bars=len(bars),
        received_bars=len(bars), last_bar_complete=True, warnings=(),
        capabilities=PUBLIC_CAPABILITIES,
    )
    return build_snapshot(batch, now=NOW, entitlement=check_data_use(
        PRIVATE_RESEARCH, "Public"))


class FakeService:
    def clock(self):
        return NOW

    def snapshot(self, symbol, horizon=3):
        return {
            "prepared": {
                "dataset": {"features": pd.DataFrame([{
                    "date": "2026-11-12", "symbol": "SPY", "open": 100.0,
                    "high": 110.0, "low": 100.0, "close": 106.0,
                }])},
                "structure": {
                    "atr": 1.0,
                    "levels": pd.DataFrame(columns=["side", "abs_distance_atr"]),
                },
            },
            "quote": {"quote": {"symbol": symbol, "last": 100.4}},
            "source": "Public",
        }

    def envelope(self, evidence, bundle=None, **meta):
        return {
            "meta": {
                "schema_version": "alphaos-research-v1",
                "symbol": (bundle or {}).get("quote", {}).get("quote", {}).get("symbol", "SPY"),
                "snapshot_id": "test-snapshot",
                "current_spot": 100.4,
            },
            "evidence": evidence,
            "caveats": [],
        }


class FakeCandles:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot
        self.error = error

    def get(self, symbol, interval, session, limit):
        if self.error:
            raise self.error
        return self.snapshot


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv("ALPHAOS_API_TOKEN", TOKEN)
    monkeypatch.setitem(api.app.state._state, "service", FakeService())
    monkeypatch.setitem(api.app.state._state, "candles", FakeCandles(candles(
        100.0, 100.2, 100.1, 101.2)))
    return TestClient(api.app)


def get(client, path="/v1/research/trade-intelligence/SPY"):
    return client.get(path, headers={"Authorization": f"Bearer {TOKEN}"})


def test_endpoint_returns_derived_contract_without_raw_candles(token):
    response = get(token)
    assert response.status_code == 200
    body = response.json()
    evidence = body["evidence"]
    assert evidence["schema_version"] == "alphaos-trade-intelligence-v1"
    assert evidence["symbol"] == "SPY"
    assert evidence["levels"]["previous_session"]["high"] == 110.0
    assert evidence["setups"][0]["state"] == "BUY"
    assert "candles" not in evidence["data"]
    assert "bars" not in evidence
    assert response.headers["cache-control"] == "no-store"


def test_authentication_and_symbol_validation_fail_before_any_provider_work(token):
    assert token.get("/v1/research/trade-intelligence/SPY").status_code == 401
    unsupported = get(token, "/v1/research/trade-intelligence/IWM")
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "unsupported_symbol"


def test_intraday_provider_failure_degrades_to_prior_session_levels(token, monkeypatch):
    monkeypatch.setitem(
        api.app.state._state, "candles",
        FakeCandles(error=MarketDataError("provider_unavailable", 503)),
    )
    response = get(token)
    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence["levels"]["previous_session"]["close"] == 106.0
    assert all(item["state"] == "WAIT" for item in evidence["setups"])
    assert any("intraday candle" in warning.lower() for warning in evidence["warnings"])


def test_openapi_exposes_the_trade_intelligence_route(token):
    paths = token.get("/openapi.json").json()["paths"]
    assert "/v1/research/trade-intelligence/{symbol}" in paths
    assert "get_trade_intelligence" == paths[
        "/v1/research/trade-intelligence/{symbol}"]["get"]["operationId"]
