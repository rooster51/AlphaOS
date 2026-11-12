"""Synthetic gateway-to-decision integration; no market or execution claims."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from modules.data_entitlements import OWNER_PRIVATE_DISPLAY, check_data_use
from modules.intraday_entry_confirmation import confirm_opening_range
from modules.market_data_contracts import CandleBar, CandleBatch
from modules.market_data_gateway import PUBLIC_CAPABILITIES, build_snapshot

OPEN = datetime(2026, 11, 12, 14, 30, tzinfo=timezone.utc)


def snapshot(*closes, symbol="SPY", complete=True, retrieved=None, start=OPEN):
    bars = tuple(
        CandleBar((start + timedelta(minutes=5*i)).isoformat(), 100,
                  max(102, close), min(98, close), close, 1000)
        for i, close in enumerate(closes)
    )
    at = retrieved or start + timedelta(minutes=5*len(bars))
    batch = CandleBatch("Public", symbol, "5m", "regular", at.isoformat(), bars,
                        None, len(bars), complete, (), PUBLIC_CAPABILITIES)
    return build_snapshot(batch, now=at)


def evaluate(snap, offset=20):
    return confirm_opening_range(snap, as_of=OPEN + timedelta(minutes=offset))


@pytest.mark.parametrize("symbol", ["SPY", "QQQ"])
@pytest.mark.parametrize("close,direction", [(103, "BUY"), (97, "SELL")])
def test_only_first_confirmed_outside_close_is_directional(symbol, close, direction):
    evidence = snapshot(100, 101, 99, close, symbol=symbol)
    result = evaluate(evidence)
    assert (result.decision, result.data_status) == (direction, "fresh")
    assert (result.opening_low, result.opening_high) == (98, 102)
    assert (result.symbol, result.snapshot_id) == (symbol, evidence.snapshot_id)
    assert result.confirmed_at == OPEN + timedelta(minutes=20)
    repeated = evaluate(snapshot(100, 101, 99, close, close), 25)
    assert (repeated.decision, repeated.reason) == ("WAIT", "break_already_seen")
    assert evaluate(snapshot(100, 101, 99, close, 100), 25).reason == "inside_range"


@pytest.mark.parametrize("close", [100, 102, 98])
def test_wicks_and_equal_closes_are_not_breaks(close):
    snap = snapshot(100, 101, 99, close)
    snap = replace(snap, candles=(*snap.candles[:-1], replace(snap.candles[-1], high=106, low=94)))
    result = evaluate(snap)
    assert (result.decision, result.reason) == ("WAIT", "inside_range")


@pytest.mark.parametrize("complete", [None, False])
def test_provider_finality_is_mandatory_even_if_window_elapsed(complete):
    result = evaluate(snapshot(100, 101, 99, 103, complete=complete))
    assert (result.decision, result.reason) == ("WAIT", "unconfirmed_close")


def test_closing_clock_cannot_rescue_bar_observed_while_still_forming():
    snap = snapshot(100, 101, 99, 103, retrieved=OPEN + timedelta(minutes=19))
    assert evaluate(snap).reason == "unconfirmed_close"


def test_snapshot_captured_after_decision_cannot_be_used_for_replay():
    result = evaluate(snapshot(100, 101, 99, 103), 19)
    assert (result.decision, result.reason) == ("WAIT", "invalid_timestamps")


def test_fresh_cached_snapshot_cannot_repeat_trigger_after_a_new_slot_elapsed():
    result = evaluate(snapshot(100, 101, 99, 103), 25)
    assert (result.decision, result.data_status, result.reason) == (
        "WAIT", "delayed", "latest_close_missing")


@pytest.mark.parametrize("bad_indices", [(1, 2, 3), (0, 2, 3), (0, 1, 1, 3), (0, 2, 1, 3)])
def test_gap_truncation_duplicate_or_reorder_fails_closed(bad_indices):
    snap = snapshot(100, 101, 99, 103)
    bad = replace(snap, candles=tuple(snap.candles[i] for i in bad_indices))
    assert evaluate(bad).reason == "incomplete_session_prefix"


def test_range_is_built_before_first_break():
    assert evaluate(snapshot(100, 101), 10).reason == "range_forming"
    assert evaluate(snapshot(100, 101, 99), 15).reason == "waiting_for_break"


@pytest.mark.parametrize("freshness,expected", [
    ("unknown", "unavailable"), ("delayed", "delayed"),
    ("stale", "stale"), ("latest_available", "stale"),
])
def test_existing_feed_freshness_is_never_promoted(freshness, expected):
    result = evaluate(replace(snapshot(100, 101, 99, 103), freshness=freshness))
    assert (result.decision, result.data_status) == ("WAIT", expected)


def test_prior_session_snapshot_is_stale_even_with_cached_freshness():
    snap = snapshot(100, 101, 99, 103, start=OPEN - timedelta(days=1))
    assert evaluate(snap).data_status == "stale"


def test_missing_and_nonresearch_snapshots_fail_closed():
    assert evaluate(None).reason == "no_snapshot"
    snap = snapshot(100, 101, 99, 103)
    display = check_data_use(OWNER_PRIVATE_DISPLAY, "Public").as_dict()
    assert evaluate(replace(snap, entitlement=display)).reason == "research_use_denied"
    assert evaluate(replace(snap, interval="1m")).reason == "unsupported_snapshot"


@pytest.mark.parametrize("instant", [
    datetime(2026, 11, 28, 15, tzinfo=timezone.utc),  # Saturday
    datetime(2026, 11, 27, 18, tzinfo=timezone.utc),  # NYSE 13:00 ET close
    OPEN - timedelta(minutes=1),
])
def test_no_confirmation_outside_regular_session(instant):
    assert confirm_opening_range(snapshot(100, 101, 99, 103), as_of=instant).reason == "session_closed"


def test_naive_decision_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        confirm_opening_range(None, as_of=OPEN.replace(tzinfo=None))
