"""Synthetic endpoint tests for the read-only trade-intelligence projection."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
from threading import Barrier, Event
from time import perf_counter

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import alphaos_api.app as api
import alphaos_api.trade_intelligence as route
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


def candles(*closes, complete=True):
    bars = []
    for index, close in enumerate(closes):
        bars.append(CandleBar(
            time=(OPEN + index * timedelta(minutes=5)).isoformat(),
            open=close - 0.05, high=close + 0.5, low=close - 0.5,
            close=close, volume=1000.0,
            provider_complete=True if index < len(closes) - 1 else None,
        ))
    batch = CandleBatch(
        provider="Public", symbol="SPY", interval="5m", session="regular",
        retrieved_at=NOW.isoformat(), bars=tuple(bars), expected_bars=len(bars),
        received_bars=len(bars), last_bar_complete=True if complete else None,
        warnings=(), capabilities=PUBLIC_CAPABILITIES,
    )
    return build_snapshot(batch, now=NOW, entitlement=check_data_use(
        PRIVATE_RESEARCH, "Public"))


class FakeService:
    def __init__(self):
        self.requested_snapshot_id = None

    def clock(self):
        return NOW

    def snapshot(self, symbol, horizon=3, snapshot_id=None):
        self.requested_snapshot_id = snapshot_id
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


def test_trade_request_reuses_the_verified_market_snapshot(token):
    service = api.app.state.service
    response = get(
        token,
        "/v1/research/trade-intelligence/SPY?snapshot_id=verified-market-snapshot",
    )
    assert response.status_code == 200
    assert service.requested_snapshot_id == "verified-market-snapshot"


def test_qqq_route_returns_the_same_versioned_contract(token):
    response = get(token, "/v1/research/trade-intelligence/QQQ")
    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence["schema_version"] == "alphaos-trade-intelligence-v1"
    assert evidence["symbol"] == "QQQ"
    assert [item["id"] for item in evidence["setups"]] == [
        "opening_range_breakout",
        "vwap_ema9_continuation",
        "support_resistance_reversal",
    ]
    assert response.headers["cache-control"] == "no-store"


def test_contract_contains_no_raw_candle_arrays_or_provider_credentials(token):
    body = get(token).json()
    forbidden_keys = {
        "candles", "bars", "ohlcv", "authorization", "token", "secret",
        "account_id", "account_number", "password",
    }

    def walk(value):
        if isinstance(value, dict):
            assert not (set(value) & forbidden_keys)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(body)
    assert "confirmed_bars" in body["evidence"]["data"]


def test_all_three_setups_wait_when_no_signal_is_confirmed(token, monkeypatch):
    monkeypatch.setitem(
        api.app.state._state, "candles",
        FakeCandles(candles(101.0, 101.2, 101.1, 102.2, complete=False)),
    )
    evidence = get(token).json()["evidence"]
    assert evidence["state"] == "WAIT"
    assert [item["id"] for item in evidence["setups"]] == [
        "opening_range_breakout",
        "vwap_ema9_continuation",
        "support_resistance_reversal",
    ]
    assert all(item["state"] == "WAIT" for item in evidence["setups"])
    assert all(item["wait_reason"] for item in evidence["setups"])
    assert all(item["options"]["status"] == "not_evaluated" for item in evidence["setups"])
    assert all(item["options"]["max_modeled_loss"] is None for item in evidence["setups"])
    assert all(item["options"]["strategy_families"] == [] for item in evidence["setups"])
    assert evidence["exit_early"]["state"] == "UNAVAILABLE"


def test_authentication_and_symbol_validation_fail_before_any_provider_work(token):
    assert token.get("/v1/research/trade-intelligence/SPY").status_code == 401
    unsupported = get(token, "/v1/research/trade-intelligence/IWM")
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "unsupported_symbol"


def test_unconfirmed_final_bar_is_excluded_by_the_endpoint(token, monkeypatch):
    monkeypatch.setitem(
        api.app.state._state, "candles",
        FakeCandles(candles(100.0, 100.2, 100.1, 101.2, complete=False)),
    )
    evidence = get(token).json()["evidence"]
    assert evidence["data"]["confirmed_bars"] == 3
    assert "last_bar_excluded_unconfirmed" in evidence["data"]["reasons"]
    breakout = next(
        item for item in evidence["setups"] if item["id"] == "opening_range_breakout"
    )
    assert breakout["state"] == "WAIT"
    assert "unverified finality" in breakout["wait_reason"]
    assert breakout["entry_trigger"] is None
    assert any("did not confirm" in warning for warning in evidence["warnings"])


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

def test_stage_timings_are_correlated_and_sanitized(token, caplog, monkeypatch):
    logger = logging.getLogger("alphaos_api.research.timing")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(logging.WARNING, logger=logger.name)
    request_id = "a" * 32
    response = token.get("/v1/research/trade-intelligence/SPY", headers={
        "Authorization": f"Bearer {TOKEN}", "X-AlphaOS-Request-ID": request_id,
    })
    assert response.status_code == 200
    assert response.headers["x-alphaos-request-id"] == request_id
    events = [json.loads(record.message) for record in caplog.records
              if record.name == "alphaos_api.research.timing"]
    assert events and all(event["request_id"] == request_id for event in events)
    durations = {event["stage"]: event["duration_ms"] for event in events
                 if event["phase"] == "end" and "duration_ms" in event}
    assert {
        "trade_research_snapshot", "trade_structure_projection", "trade_5m_candles",
        "trade_intelligence_calculation", "trade_response_envelope", "response_serialization",
    } <= durations.keys()
    assert all(value >= 0 for value in durations.values())
    assert TOKEN not in caplog.text
    assert "current_spot" not in caplog.text and "candles" not in response.json()["evidence"]["data"]


@pytest.mark.parametrize("slow_stage", ["snapshot", "candles"])
def test_slow_dependency_returns_bounded_failure(token, monkeypatch, slow_stage):
    started = Event()
    release = Event()
    finished = Event()

    def slow(*args, **kwargs):
        started.set()
        try:
            release.wait(5)
        finally:
            finished.set()

    target = api.app.state.service if slow_stage == "snapshot" else api.app.state.candles
    monkeypatch.setattr(target, "snapshot" if slow_stage == "snapshot" else "get", slow)
    monkeypatch.setattr(route, "TRADE_INTELLIGENCE_BUDGET_SECONDS", 0.2)
    began = perf_counter()
    try:
        response = get(token)
        assert started.is_set()
        assert not finished.is_set()
        assert perf_counter() - began < 2
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "trade_intelligence_timeout"
        assert "evidence" not in response.json()
    finally:
        release.set()
        assert finished.wait(2)


def test_timed_out_workers_hold_capacity_until_they_exit(token, monkeypatch):
    entered = Barrier(3)
    release = Event()
    finished = Barrier(3)

    def slow_snapshot(*args, **kwargs):
        entered.wait(5)
        release.wait(5)
        finished.wait(5)

    monkeypatch.setattr(api.app.state.service, "snapshot", slow_snapshot)
    monkeypatch.setattr(route, "TRADE_INTELLIGENCE_BUDGET_SECONDS", 0.5)
    with ThreadPoolExecutor(max_workers=2) as callers:
        try:
            spy = callers.submit(get, token)
            qqq = callers.submit(get, token, "/v1/research/trade-intelligence/QQQ")
            entered.wait(2)
            assert spy.result(2).status_code == qqq.result(2).status_code == 504
            rejected = get(token)
            assert rejected.status_code == 503
            assert rejected.json()["error"]["code"] == "trade_intelligence_busy"
            assert token.get("/health").status_code == 200
        finally:
            release.set()
            finished.wait(2)
