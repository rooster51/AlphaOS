"""Regression checks for opt-in time-closed research; never authorizes signals."""
from dataclasses import replace
from datetime import datetime, timezone

from modules.market_data_contracts import CandleBar, CandleSnapshot
from modules.time_closed_candles import time_closed_research


def _snapshot(at, bars):
    return CandleSnapshot(
        schema_version="1", symbol="SPY", interval="5m", provider="public",
        session="regular", retrieved_at=at, latest_candle_at=None,
        snapshot_id="fixture", expected_bars=None, received_bars=len(bars),
        returned_bars=len(bars), completeness="unknown", last_bar_status="unknown",
        freshness="fresh", warnings=("provider_live_tail_excluded",),
        candles=tuple(bars), provider_capabilities={},
        entitlement={"allowed": True, "provider": "public"},
    )


def test_time_close_is_opt_in_and_never_actionable():
    bar = CandleBar("2026-11-17T14:30:00+00:00", 100, 101, 99, 100, 1000)
    a = _snapshot("2026-11-17T14:35:02+00:00", [bar])
    b = _snapshot("2026-11-17T14:35:06+00:00", [bar])
    now = datetime(2026, 11, 17, 14, 35, 6, tzinfo=timezone.utc)
    assert time_closed_research(a, b, now=now).reason == "time_closed_mode_disabled"
    result = time_closed_research(a, b, now=now, enabled=True)
    assert result.evidence == "closed_by_time"
    assert len(result.bars) == 1
    assert result.actionable is False
    assert result.bars[0].provider_complete is None


def test_open_tail_excluded_and_close_grace():
    bar = CandleBar("2026-11-17T14:30:00+00:00", 100, 101, 99, 100, 1000)
    tail = replace(bar, time="2026-11-17T14:35:00+00:00")
    a = _snapshot("2026-11-17T14:35:01+00:00", [bar, tail])
    b = _snapshot("2026-11-17T14:35:04+00:00", [bar, tail])
    now = datetime(2026, 11, 17, 14, 35, 4, tzinfo=timezone.utc)
    assert not time_closed_research(a, b, now=now, enabled=True).bars
    b = replace(b, retrieved_at="2026-11-17T14:35:06+00:00")
    result = time_closed_research(a, b, now=now.replace(second=6), enabled=True)
    assert len(result.bars) == 1


def test_revisions_fail_closed():
    bar = CandleBar("2026-11-17T14:30:00+00:00", 100, 101, 99, 100, 1000)
    changed = replace(bar, close=100.5)
    a = _snapshot("2026-11-17T14:35:02+00:00", [bar])
    b = _snapshot("2026-11-17T14:35:06+00:00", [changed])
    now = datetime(2026, 11, 17, 14, 35, 6, tzinfo=timezone.utc)
    result = time_closed_research(a, b, now=now, enabled=True)
    assert result.reason == "bar_revised_on_refetch"
    assert result.bars == ()
