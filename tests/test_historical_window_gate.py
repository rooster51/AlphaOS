"""Fail-closed historical window boundary regression tests."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from modules.historical_window_gate import _window, evaluate_verified_historical_windows
from modules.intraday_quoted_round_trip import EvidenceRejected


@pytest.mark.parametrize("value", [
    {"start": "2026-10-09T09:30:00", "end": "2026-10-09T09:35:00-04:00"},
    {"start": "2026-10-09T09:35:00-04:00", "end": "2026-10-09T09:30:00-04:00"},
    {"start": "2026-10-09T08:30:00-04:00", "end": "2026-10-09T09:35:00-04:00"},
    {"start": "2026-10-09T15:59:00-04:00", "end": "2026-10-12T09:31:00-04:00"},
    {"start": "2026-10-10T09:30:00-04:00", "end": "2026-10-10T09:35:00-04:00"},
])
def test_reject_invalid_windows(value):
    with pytest.raises(EvidenceRejected):
        _window(value)


def test_valid_regular_session_window():
    start, end = _window({"start": "2026-10-09T09:30:00-04:00",
                          "end": "2026-10-09T09:35:00-04:00"})
    assert start == datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)
    assert end > start


def test_reject_overlapping_windows_before_evaluation():
    with pytest.raises(EvidenceRejected, match="overlapping"):
        evaluate_verified_historical_windows({}, {}, [], entry_window={
            "start": "2026-10-09T09:30:00-04:00", "end": "2026-10-09T09:35:00-04:00"
        }, exit_window={
            "start": "2026-10-09T09:34:00-04:00", "end": "2026-10-09T09:40:00-04:00"
        })


def test_reject_snapshot_outside_window_without_fallback():
    entry = {"payload": {"observed_at": "2026-10-09T13:29:00Z"},
             "metadata": {"created_at": "2026-10-09T13:31:00Z"}}
    exit = {"payload": {"observed_at": "2026-10-09T13:40:00Z"},
            "metadata": {"created_at": "2026-10-09T13:41:00Z"}}
    with patch("modules.historical_window_gate.reconstruct_quoted_round_trip") as evaluator:
        with pytest.raises(EvidenceRejected, match="archive_outside_requested_window"):
            evaluate_verified_historical_windows(entry, exit, [], entry_window={
                "start": "2026-10-09T09:30:00-04:00", "end": "2026-10-09T09:35:00-04:00"
            }, exit_window={
                "start": "2026-10-09T09:40:00-04:00", "end": "2026-10-09T09:45:00-04:00"
            })
        evaluator.assert_not_called()
