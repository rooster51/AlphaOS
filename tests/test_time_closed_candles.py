"""Regression checks for opt-in time-closed research; never authorizes signals."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from modules.market_data_contracts import CandleBar, CandleSnapshot
from modules.time_closed_candles import time_closed_research


def _snapshot(at, bars):
    return CandleSnapshot(
        schema_version="1", symbol="SPY", interval="5m", provider="Public",
        session="regular", retrieved_at=at, latest_candle_at=None,
        snapshot_id="fixture", expected_bars=None, received_bars=len(bars),
        returned_bars=len(bars), completeness="unknown", last_bar_status="unknown",
        freshness="fresh", warnings=("provider_live_tail_excluded",),
        candles=tuple(bars), provider_capabilities={},
        entitlement={"allowed": True, "provider": "Public"},
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


def test_provisional_indicators_are_not_verified_signals():
    bars = [
        CandleBar(
            f"2026-11-17T{14 + (30 + i * 5) // 60:02d}:{(30 + i * 5) % 60:02d}:00+00:00",
            100 + i, 101 + i, 99 + i, 100 + i, 1000,
        )
        for i in range(10)
    ]
    first = _snapshot("2026-11-17T15:20:01+00:00", bars)
    second = _snapshot("2026-11-17T15:20:06+00:00", bars)
    now = datetime(2026, 11, 17, 15, 20, 6, tzinfo=timezone.utc)
    result = time_closed_research(first, second, now=now, enabled=True)
    assert len(result.bars) == 10
    assert result.opening_range["high"] == 103
    assert result.vwap == pytest.approx(104.5)
    assert result.ema9 == pytest.approx(105)
    assert result.actionable is False
    assert result.evidence == "closed_by_time"


def test_refetch_arriving_after_grace_must_start_after_grace():
    bar = CandleBar("2026-11-17T14:30:00+00:00", 100, 101, 99, 100, 1000)
    first = _snapshot("2026-11-17T14:35:02+00:00", [bar])
    second = _snapshot("2026-11-17T14:35:06+00:00", [bar])
    now = datetime(2026, 11, 17, 14, 35, 7, tzinfo=timezone.utc)
    result = time_closed_research(
        first, second, now=now, enabled=True, refetch_started_at=now.replace(second=4),
    )
    assert result.reason == "no_elapsed_refetched_bars"


def test_refetch_source_mismatch_fails_closed():
    bar = CandleBar("2026-11-17T14:30:00+00:00", 100, 101, 99, 100, 1000)
    a = _snapshot("2026-11-17T14:35:02+00:00", [bar])
    b = replace(_snapshot("2026-11-17T14:35:06+00:00", [bar]),
                symbol="QQQ")
    now = datetime(2026, 11, 17, 14, 35, 7, tzinfo=timezone.utc)
    assert time_closed_research(a, b, now=now, enabled=True).reason == "refetch_source_mismatch"


@pytest.mark.parametrize(("change", "reason"), [
    ({"freshness": "stale"}, "invalid_snapshot_contract"),
    ({"completeness": "incomplete"}, "invalid_snapshot_contract"),
    ({"warnings": ("provider_incomplete_bars_skipped",)}, "invalid_snapshot_contract"),
])
def test_invalid_snapshot_fails_closed(change, reason):
    bar = CandleBar("2026-11-17T14:30:00+00:00", 100, 101, 99, 100, 1000)
    first = _snapshot("2026-11-17T14:40:05+00:00", [bar])
    second = replace(first, **change)
    now = datetime.fromisoformat(first.retrieved_at)
    assert time_closed_research(first, second, now=now, enabled=True).reason == reason


@pytest.mark.parametrize(("day", "hour", "reason"), [
    ("2026-11-17", 14, "missing_or_unmatched_interval"),
    ("2026-07-06", 13, "missing_or_unmatched_interval"),
    ("2026-07-03", 13, "no_authoritative_session"),
])
def test_missing_bar_uses_authoritative_session_grid(day, hour, reason):
    bar = CandleBar(f"{day}T{hour}:30:00+00:00", 100, 101, 99, 100, 1000)
    snap = _snapshot(f"{day}T{hour}:40:05+00:00", [bar])
    now = datetime.fromisoformat(snap.retrieved_at)
    assert time_closed_research(snap, snap, now=now, enabled=True).reason == reason


def test_early_close_caps_eligible_intervals():
    opening = datetime(2026, 11, 27, 14, 30, tzinfo=timezone.utc)
    bars = [
        CandleBar((opening + timedelta(minutes=5 * i)).isoformat(), 100, 101, 99, 100, 1000)
        for i in range(42)
    ]
    now = datetime(2026, 11, 27, 18, 10, tzinfo=timezone.utc)
    snap = replace(_snapshot(now.isoformat(), bars), freshness="latest_available")
    assert len(time_closed_research(snap, snap, now=now, enabled=True).bars) == 42
