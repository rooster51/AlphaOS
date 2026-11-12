"""Synthetic Phase A contracts: no Public network calls or credentials."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from modules.data_entitlements import (
    AI_ANALYSIS,
    COMMERCIAL_USE,
    OWNER_PRIVATE_DISPLAY,
    PRIVATE_RESEARCH,
    PUBLIC_DISPLAY,
    REDISTRIBUTION,
    DataUseDenied,
    EntitlementDecision,
    ai_evidence_allowed,
    archive_write_allowed,
    check_data_use,
    export_allowed,
)
from modules.market_data_contracts import (
    INTERVAL_SECONDS,
    SUPPORTED_INTERVALS,
    SUPPORTED_SYMBOLS,
    CandleBar,
    CandleBatch,
    ProviderCapabilities,
)
from modules.market_data_gateway import (
    MarketDataError,
    PublicMarketDataProvider,
    build_snapshot,
)
from modules.supabase_archive import persist_candles

NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
CLOSED = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)
SYNTHETIC_ENTITLEMENT = EntitlementDecision(
    provider="SyntheticFeed",
    use_context=PRIVATE_RESEARCH,
    allowed=True,
    code="allowed",
    reason="Synthetic test entitlement.",
    basis="Synthetic test fixture only.",
)
CAPS = ProviderCapabilities(
    provider="SyntheticFeed",
    symbols=SUPPORTED_SYMBOLS,
    intervals=SUPPORTED_INTERVALS,
    sessions=("regular",),
    latest_quotes=True,
    native_candles=True,
    provider_native_intervals=True,
    expected_bar_metadata=True,
    entitlement={},
)


def bar(minute: int, *, close=None, high=None, low=None, volume=100.0):
    value = 100.0 + minute / 100
    return CandleBar(
        time=datetime(2026, 10, 2, 13, 30, tzinfo=timezone.utc).replace(minute=30 + minute).isoformat(),
        open=value,
        high=high if high is not None else value + 0.5,
        low=low if low is not None else value - 0.5,
        close=close if close is not None else value + 0.1,
        volume=volume,
    )


def batch(*bars, expected=3, last_complete=None, provider="SyntheticFeed", warnings=()):
    return CandleBatch(
        provider=provider,
        symbol="SPY",
        interval="1m",
        session="regular",
        retrieved_at=NOW.isoformat(),
        bars=tuple(bars),
        expected_bars=expected,
        received_bars=len(bars),
        last_bar_complete=last_complete,
        warnings=tuple(warnings),
        capabilities=CAPS,
    )


def test_private_and_owner_private_display_are_allowed_but_public_uses_are_denied():
    assert check_data_use(PRIVATE_RESEARCH, "Public").allowed
    owner_private = check_data_use(OWNER_PRIVATE_DISPLAY, "Public")
    assert owner_private.allowed
    assert owner_private.authorization_required is False
    assert owner_private.authorization_reference_present is False
    for use in (PUBLIC_DISPLAY, COMMERCIAL_USE, REDISTRIBUTION, AI_ANALYSIS):
        decision = check_data_use(use, "Public")
        assert not decision.allowed
        assert decision.code == "data_use_denied"
    assert archive_write_allowed("Public").allowed
    with pytest.raises(DataUseDenied):
        export_allowed("Public")
    with pytest.raises(DataUseDenied):
        ai_evidence_allowed("Public")
    assert not check_data_use("unknown_use", "Public").allowed
    assert not check_data_use(PRIVATE_RESEARCH, "UnknownFeed").allowed
    assert not check_data_use(OWNER_PRIVATE_DISPLAY, "UnknownFeed").allowed


class RecordingArchiveClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        self.calls.append(name)
        raise AssertionError("archive client must not be touched")


def archive_row(provider, *, symbol="SPY"):
    return dict(provider=provider, symbol=symbol, aggregation="ONE_MINUTE",
                timestamp=NOW.isoformat(), open=1, high=1, low=1, close=1, volume=1,
                retrieved_at=NOW.isoformat())


def test_archive_guard_runs_before_supabase_client_access():
    with pytest.raises(DataUseDenied):
        persist_candles(RecordingArchiveClient(), [archive_row("UnknownFeed")])


def test_archive_rejects_mixed_provider_batches_before_any_write():
    client = RecordingArchiveClient()
    rows = [archive_row("Public"), archive_row("UnknownFeed")]
    with pytest.raises(ValueError, match="exactly one provider"):
        persist_candles(client, rows)
    assert client.calls == []


def test_archive_rejects_a_batch_with_a_missing_provider_before_any_write():
    client = RecordingArchiveClient()
    row = archive_row("Public")
    del row["provider"]
    with pytest.raises(ValueError, match="provider is required"):
        persist_candles(client, [row])
    assert client.calls == []


def test_snapshot_contract_is_provider_independent_and_quality_explicit():
    snapshot = build_snapshot(batch(bar(0), bar(1), bar(2), last_complete=False), now=CLOSED,
                              entitlement=SYNTHETIC_ENTITLEMENT)
    payload = snapshot.as_dict()
    assert payload["schema_version"] == "alphaos-candles-v1"
    assert payload["provider"] == "SyntheticFeed"
    assert payload["completeness"] == "complete"
    assert payload["last_bar_status"] == "partial"
    assert payload["returned_bars"] == payload["received_bars"] == 3
    assert payload["expected_bars"] == 3
    assert payload["provider_capabilities"]["native_candles"] is True
    assert payload["entitlement"]["allowed"] is True
    assert payload["candles"][0]["time"].endswith("+00:00")
    assert payload["snapshot_id"] == build_snapshot(
        batch(bar(0), bar(1), bar(2), last_complete=False), now=NOW,
        entitlement=SYNTHETIC_ENTITLEMENT).snapshot_id


def test_snapshot_marks_incomplete_and_missing_bars_without_filling():
    snapshot = build_snapshot(batch(bar(0), bar(2), warnings=("missing_bars",)),
                              now=CLOSED, entitlement=SYNTHETIC_ENTITLEMENT)
    assert snapshot.completeness == "incomplete"
    assert "missing_bars" in snapshot.warnings
    assert "incomplete_session" in snapshot.warnings
    assert "session_in_progress" not in snapshot.warnings
    assert len(snapshot.candles) == 2


def test_snapshot_does_not_claim_completion_without_provider_evidence():
    snapshot = build_snapshot(batch(bar(0), bar(1), bar(2)), now=NOW, entitlement=SYNTHETIC_ENTITLEMENT)
    assert snapshot.last_bar_status == "unknown"
    assert "last_bar_completion_unverified" in snapshot.warnings


def test_last_bar_status_uses_provider_evidence_only():
    complete = build_snapshot(batch(bar(0), last_complete=True), now=NOW,
                              entitlement=SYNTHETIC_ENTITLEMENT)
    partial = build_snapshot(batch(bar(0), last_complete=False), now=NOW,
                             entitlement=SYNTHETIC_ENTITLEMENT)
    unknown = build_snapshot(batch(bar(0), last_complete=None), now=NOW,
                             entitlement=SYNTHETIC_ENTITLEMENT)
    assert complete.last_bar_status == "complete"
    assert partial.last_bar_status == "partial"
    assert unknown.last_bar_status == "unknown"


def test_clock_only_open_interval_is_a_warning_not_a_partial_classification():
    snapshot = build_snapshot(batch(bar(0)), now=datetime(2026, 10, 2, 13, 30, 30, tzinfo=timezone.utc),
                              entitlement=SYNTHETIC_ENTITLEMENT)
    assert snapshot.last_bar_status == "unknown"
    assert "last_bar_completion_unverified" in snapshot.warnings
    assert "last_bar_window_open" in snapshot.warnings


def test_in_progress_session_is_unknown_not_incomplete():
    snapshot = build_snapshot(batch(bar(0), bar(1), expected=390), now=NOW,
                              entitlement=SYNTHETIC_ENTITLEMENT)
    assert snapshot.completeness == "unknown"
    assert "session_in_progress" in snapshot.warnings
    assert "incomplete_session" not in snapshot.warnings


def test_completed_session_with_missing_bars_is_incomplete():
    snapshot = build_snapshot(batch(bar(0), bar(1), expected=390), now=CLOSED,
                              entitlement=SYNTHETIC_ENTITLEMENT)
    assert snapshot.completeness == "incomplete"
    assert "session_in_progress" not in snapshot.warnings
    assert "incomplete_session" in snapshot.warnings


def test_snapshot_identity_changes_when_data_changes():
    first = build_snapshot(batch(bar(0), bar(1)), now=NOW, entitlement=SYNTHETIC_ENTITLEMENT)
    second = build_snapshot(batch(bar(0), bar(1, close=101.0)), now=NOW, entitlement=SYNTHETIC_ENTITLEMENT)
    assert first.snapshot_id != second.snapshot_id


def test_public_quote_normalization_uses_normalized_contract(monkeypatch):
    import modules.market_data_gateway as gateway
    monkeypatch.setattr(gateway, "get_public_quotes", lambda symbols, _context=None: [dict(
        symbol="SPY", last=600.0, bid=599.9, ask=600.1, previous_close=598.0,
        change=2.0, change_pct=0.33, volume=1000, updated_at="2026-10-02T13:59:30Z",
        retrieved_at="2026-10-02T14:00:00Z")])
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: NOW)
    quote = provider.quote("SPY")
    assert quote.symbol == "SPY"
    assert quote.last == 600.0
    assert quote.session == "regular_session"
    assert quote.freshness == "fresh"
    assert quote.warnings == ()


@pytest.mark.parametrize("interval", SUPPORTED_INTERVALS)
def test_public_candle_adapter_normalizes_each_interval(monkeypatch, interval):
    import modules.market_data_gateway as gateway
    step = INTERVAL_SECONDS[interval]
    start = datetime(2026, 10, 2, 13, 30, tzinfo=timezone.utc)
    rows = [dict(
        symbol="QQQ", aggregation=gateway.AGGREGATION_BY_INTERVAL[interval],
        timestamp=start.isoformat(), open=500, high=501, low=499,
        close=500.5, volume=10, provider_expected_bars=3,
        provider_skipped_incomplete_bars=0,
    ), dict(
        symbol="QQQ", aggregation=gateway.AGGREGATION_BY_INTERVAL[interval],
        timestamp=(start + __import__("datetime").timedelta(seconds=step)).isoformat(),
        open=500.5, high=501, low=500,
        close=500.8, volume=12, provider_expected_bars=3,
        provider_skipped_incomplete_bars=0,
    )]
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {
        "provider_expected_bars": 3, "provider_received_bars": 2,
        "provider_skipped_incomplete_bars": 0}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: NOW)
    result = provider.candles("QQQ", interval, "regular", 390)
    assert result.symbol == "QQQ"
    assert result.interval == interval
    assert result.expected_bars == 3
    assert result.received_bars == 2
    snapshot = build_snapshot(result, now=CLOSED)
    assert snapshot.completeness == "incomplete"
    assert "incomplete_session" in snapshot.warnings


@pytest.mark.parametrize("mutation,code", [
    ("duplicate", "duplicate_candle_timestamp"),
    ("order", "candle_timestamp_out_of_order"),
    ("ohlc", "candle_ohlc_invalid"),
    ("ohlc_missing", "candle_ohlc_missing"),
    ("session", "candle_outside_regular_session"),
    ("interval", "candle_interval_misaligned"),
    ("timestamp", "candle_timestamp_invalid"),
    ("symbol", "candle_symbol_mismatch"),
    ("aggregation", "candle_aggregation_mismatch"),
])
def test_public_candle_validation_fails_closed(monkeypatch, mutation, code):
    import modules.market_data_gateway as gateway
    rows = [dict(symbol="SPY", aggregation="ONE_MINUTE", timestamp="2026-10-02T13:30:00+00:00",
                 open=500, high=501, low=499, close=500.5, volume=10,
                 provider_expected_bars=2), dict(
                 symbol="SPY", aggregation="ONE_MINUTE", timestamp="2026-10-02T13:31:00+00:00",
                 open=500, high=500.2, low=499, close=500.5, volume=11,
                 provider_expected_bars=2)]
    if mutation == "duplicate":
        rows[1]["timestamp"] = rows[0]["timestamp"]
    elif mutation == "order":
        rows[0]["timestamp"], rows[1]["timestamp"] = rows[1]["timestamp"], rows[0]["timestamp"]
    elif mutation == "ohlc":
        rows[1]["high"] = 499.5
    elif mutation == "ohlc_missing":
        rows[0]["volume"] = None
    elif mutation == "session":
        rows[0]["timestamp"] = "2026-10-02T12:00:00+00:00"
    elif mutation == "interval":
        rows[0]["timestamp"] = "2026-10-02T13:30:30+00:00"
    elif mutation == "timestamp":
        rows[0]["timestamp"] = "not-a-timestamp"
    elif mutation == "symbol":
        rows[0]["symbol"] = "QQQ"
    elif mutation == "aggregation":
        rows[0]["aggregation"] = "FIVE_MINUTES"
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: NOW)
    with pytest.raises(MarketDataError) as error:
        provider.candles("SPY", "1m")
    assert error.value.code == code


def test_out_of_session_error_reports_safe_relation_not_payload(monkeypatch):
    import modules.market_data_gateway as gateway
    rows = [dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T13:29:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10, provider_expected_bars=2)]
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: NOW)
    with pytest.raises(MarketDataError) as error:
        provider.candles("SPY", "1m")
    assert error.value.code == "candle_outside_regular_session"
    assert error.value.detail == {
        "bar_index": 0, "bar_count": 1, "relation": "before_open",
        "minutes_before_open": 1,
    }
    assert "2026-10-02T13:29:00" not in str(error.value.detail)


def test_public_closing_bar_is_excluded_without_weakening_other_session_checks(monkeypatch):
    import modules.market_data_gateway as gateway
    rows = [dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T19:59:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10, provider_expected_bars=2),
            dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T20:00:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10, provider_expected_bars=2)]
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: CLOSED)
    result = provider.candles("SPY", "1m", "regular", 390)
    assert len(result.bars) == 1
    assert result.bars[0].time == "2026-10-02T19:59:00+00:00"
    assert result.expected_bars == 1
    assert result.received_bars == 1
    assert "provider_closing_bar_excluded" in result.warnings
    assert "provider_expected_bars_adjusted_for_closing_bar" in result.warnings
    snapshot = build_snapshot(result, now=CLOSED)
    assert snapshot.completeness == "complete"
    assert "provider_closing_bar_excluded" in snapshot.warnings

    rows[-1]["timestamp"] = "2026-10-02T20:01:00+00:00"
    with pytest.raises(MarketDataError) as error:
        provider.candles("SPY", "1m", "regular", 390)
    assert error.value.code == "candle_outside_regular_session"
    assert error.value.detail["relation"] == "after_close"
    assert error.value.detail["minutes_after_close"] == 1


def test_provider_intraday_diagnostic_is_preserved(monkeypatch):
    import modules.market_data_gateway as gateway
    from modules.public_intraday import PublicIntradayError
    def fail(*args, **kwargs):
        raise PublicIntradayError("provider_bars_timestamp_naive")
    monkeypatch.setattr(gateway, "fetch_intraday_bars", fail)
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: NOW)
    with pytest.raises(MarketDataError) as error:
        provider.candles("SPY", "1m")
    assert error.value.code == "provider_bars_timestamp_naive"


def test_public_candle_limit_narrows_returned_bars_not_provider_counts(monkeypatch):
    import modules.market_data_gateway as gateway
    rows = []
    for minute in range(5):
        stamp = datetime(2026, 10, 2, 13, 55 + minute, tzinfo=timezone.utc)
        rows.append(dict(symbol="SPY", aggregation="ONE_MINUTE", timestamp=stamp.isoformat(),
                         open=500, high=501, low=499, close=500.5, volume=10,
                         provider_expected_bars=5))
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {
        "provider_expected_bars": 5, "provider_received_bars": 5,
        "provider_skipped_incomplete_bars": 0}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc))
    result = provider.candles("SPY", "1m", "regular", 2)
    assert result.received_bars == 5
    assert len(result.bars) == 2
    snapshot = build_snapshot(result, now=datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc))
    assert snapshot.returned_bars == 2
    assert snapshot.completeness == "complete"


def test_provider_skipped_rows_are_reported_and_completed_session_is_incomplete(monkeypatch):
    import modules.market_data_gateway as gateway
    rows = [dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T19:58:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10, provider_expected_bars=390),
            dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T19:59:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10, provider_expected_bars=390)]
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {
        "provider_expected_bars": 390, "provider_received_bars": 390,
        "provider_skipped_incomplete_bars": 1}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: CLOSED)
    result = provider.candles("SPY", "1m", "regular", 390)
    assert "provider_incomplete_bars_skipped" in result.warnings
    snapshot = build_snapshot(result, now=CLOSED)
    assert snapshot.completeness == "incomplete"
    assert "incomplete_session" in snapshot.warnings


def test_expected_count_from_diagnostics_is_not_reported_as_unavailable(monkeypatch):
    import modules.market_data_gateway as gateway
    rows = [dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T19:58:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10),
            dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T19:59:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10)]
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {
        "provider_expected_bars": 2, "provider_received_bars": 2,
        "provider_skipped_incomplete_bars": 0}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: CLOSED)
    result = provider.candles("SPY", "1m", "regular", 390)
    assert result.expected_bars == 2
    assert "expected_bar_count_unavailable" not in result.warnings
    snapshot = build_snapshot(result, now=CLOSED)
    assert snapshot.completeness == "complete"
    assert "expected_bar_count_unavailable" not in snapshot.warnings


def test_unknown_or_unsupported_requests_are_rejected_without_provider_calls():
    provider = PublicMarketDataProvider(context=lambda: (_ for _ in ()).throw(AssertionError("must not authenticate")),
                                        clock=lambda: NOW)
    with pytest.raises(MarketDataError) as error:
        provider.candles("IWM", "1m")
    assert error.value.code == "unsupported_symbol"
    with pytest.raises(MarketDataError) as error:
        provider.candles("SPY", "30m")
    assert error.value.code == "unsupported_interval"


def test_expected_bar_count_conflict_is_distinct(monkeypatch):
    import modules.market_data_gateway as gateway
    rows = [dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T13:30:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10, provider_expected_bars=2),
            dict(symbol="SPY", aggregation="ONE_MINUTE",
                 timestamp="2026-10-02T13:31:00+00:00", open=500, high=501, low=499,
                 close=500.5, volume=10, provider_expected_bars=3)]
    monkeypatch.setattr(gateway, "fetch_intraday_bars", lambda *args, **kwargs: (rows, {}))
    provider = PublicMarketDataProvider(context=lambda: (object(), "synthetic-account"),
                                        clock=lambda: NOW)
    with pytest.raises(MarketDataError) as error:
        provider.candles("SPY", "1m")
    assert error.value.code == "candle_expected_bars_conflict"
