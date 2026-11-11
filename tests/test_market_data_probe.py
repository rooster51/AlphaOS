"""Probe tests use a fake provider except for the explicit no-credential path."""
from __future__ import annotations

from datetime import datetime, timezone

from modules.market_data_contracts import (
    INTERVAL_SECONDS,
    SUPPORTED_INTERVALS,
    SUPPORTED_SYMBOLS,
    CandleBar,
    CandleBatch,
    ProviderCapabilities,
)
from modules.market_data_gateway import build_snapshot
from modules.data_entitlements import PRIVATE_RESEARCH, EntitlementDecision
from scripts.market_data_probe import main, probe_once, summarize

NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
CLOSED = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)


class FakeProvider:
    name = "Public"
    capabilities = ProviderCapabilities(
        provider="Public",
        symbols=SUPPORTED_SYMBOLS,
        intervals=SUPPORTED_INTERVALS,
        sessions=("regular",),
        latest_quotes=True,
        native_candles=True,
        provider_native_intervals=True,
        expected_bar_metadata=True,
        entitlement={},
    )

    def quote(self, symbol):
        from modules.market_data_gateway import QuoteObservation
        return QuoteObservation(
            provider="Public", symbol=symbol, last=600.0,
            bid=599.9, ask=600.1, previous_close=598.0, change=2.0,
            change_pct=0.33, volume=1000, quote_time="2026-10-02T13:59:30+00:00",
            retrieved_at=NOW.isoformat(), session="regular_session",
            market_state="regular_open", freshness="fresh",
            freshness_reason="within_active_age_limit", warnings=(),
        )

    def candles(self, symbol, interval, session="regular", limit=390):
        bars = (
            CandleBar("2026-10-02T13:30:00+00:00", 500, 501, 499, 500.5, 10),
            CandleBar("2026-10-02T13:31:00+00:00", 500.5, 501, 500, 500.8, 12),
        )
        return CandleBatch(
            provider="Public", symbol=symbol, interval=interval, session=session,
            retrieved_at=NOW.isoformat(), bars=bars, expected_bars=3,
            received_bars=2, last_bar_complete=None, warnings=("missing_bars",),
            capabilities=self.capabilities,
        )


def test_probe_reports_normalized_measurements_and_quality():
    result = probe_once(FakeProvider(), "SPY", "1m", clock=lambda: CLOSED)
    assert result["available"] is True
    assert result["quote_latency_ms"] is not None
    assert result["candle_latency_ms"] is not None
    assert result["received_bars"] == 2
    assert result["completeness"] == "incomplete"
    assert "missing_bars" in result["warnings"]


def test_probe_summary_keeps_errors_and_quality_codes():
    rows = [
        dict(symbol="SPY", interval="1m", available=True, error=None,
             quote_latency_ms=10, candle_latency_ms=20,
             quote_to_candle_lag_seconds=5, completeness="complete",
             last_bar_status="unknown", freshness="fresh", warnings=[]),
        dict(symbol="SPY", interval="1m", available=False, error="public_rate_limit",
             quote_latency_ms=None, candle_latency_ms=None,
             quote_to_candle_lag_seconds=None, completeness=None,
             last_bar_status=None, freshness=None, warnings=[]),
    ]
    summary = summarize(rows)
    assert summary[0]["samples"] == 2
    assert summary[0]["available_samples"] == 1
    assert summary[0]["errors"] == ["public_rate_limit"]
    assert summary[0]["completeness"] == ["complete"]


def test_probe_without_credentials_does_not_invent_measurements(monkeypatch, capsys):
    monkeypatch.delenv("PUBLIC_API_SECRET", raising=False)
    assert main(["--samples", "1"], provider=None) == 2
    text = capsys.readouterr().out
    assert "public_not_configured" in text
    assert '"measured": false' in text
    assert '"quote_latency_ms"' not in text
