import json
from datetime import datetime, timezone

import pytest

from modules.candle_integrity import (
    CAVEATS,
    audit_candle_rows,
    summarize_report,
    validated_bars,
)


def row(second=0, **overrides):
    values = {
        "provider": "Public",
        "symbol": "SPY",
        "aggregation": "ONE_MINUTE",
        "bar_time": f"2026-11-02T15:30:{second:02d}+00:00",
        "open": 500.0,
        "high": 501.0,
        "low": 499.5,
        "close": 500.5,
        "volume": 1200.0,
        "retrieved_at": "2026-11-02T15:31:00+00:00",
    }
    values.update(overrides)
    return values


def test_identical_duplicate_minute_bucket_is_reported_but_kept_raw():
    rows = [row(0), row(37)]
    report = audit_candle_rows(rows)

    assert report["raw_row_count"] == 2
    assert report["bucket_count"] == 1
    assert report["duplicate_bucket_count"] == 1
    assert report["identical_duplicate_bucket_count"] == 1
    assert report["conflicting_bucket_count"] == 0
    assert report["validated_bar_count"] == 1
    assert report["buckets"][0]["state"] == "duplicate_identical"
    assert report["buckets"][0]["observation_count"] == 2
    # Both raw observations survive, including their different timestamps.
    assert [item["raw"]["bar_time"] for item in report["buckets"][0]["observations"]] == [
        "2026-11-02T15:30:00+00:00",
        "2026-11-02T15:30:37+00:00",
    ]


def test_conflicting_duplicate_bucket_is_never_a_validated_bar():
    rows = [row(0, close=500.5), row(12, close=500.9)]
    report = audit_candle_rows(rows)

    assert report["conflicting_bucket_count"] == 1
    assert report["identical_duplicate_bucket_count"] == 0
    assert report["validated_bar_count"] == 0
    bucket = report["buckets"][0]
    assert bucket["state"] == "duplicate_conflicting"
    assert bucket["bar"] is None
    assert [item["bar"]["close"] for item in bucket["observations"]] == [500.5, 500.9]
    assert validated_bars(report) == []


def test_invalid_observations_are_reported_with_their_raw_rows():
    rows = [
        row(0, high=498.0),  # high below low
        dict(row(0), bar_time="2026-11-02T15:31:00+00:00", volume=-1),
        row(120, close=None),
        dict(row(180), bar_time="2026-11-02T15:33:00"),  # naive timestamp
        dict(row(240), provider=""),
        "not-a-row",
    ]
    report = audit_candle_rows(rows)

    assert report["validated_bar_count"] == 0
    assert report["invalid_row_count"] == 6
    reasons = [item["reason"] for item in report["invalid_rows"]]
    assert reasons == [
        "high_below_low",
        "negative_volume",
        "missing_or_invalid_price",
        "invalid_or_naive_timestamp",
        "invalid_identity",
        "row_not_object",
    ]
    # Raw payloads stay in the report for follow-up investigation.
    assert report["invalid_rows"][0]["raw"]["high"] == 498.0
    assert report["invalid_rows"][5]["raw"] == "not-a-row"


def test_minute_bucketing_separates_distinct_minutes_and_series():
    rows = [
        row(0),
        row(0, symbol="QQQ"),
        row(0, aggregation="FIVE_MINUTES"),
        dict(row(0), bar_time="2026-11-02T15:31:00+00:00"),
    ]
    report = audit_candle_rows(rows)

    assert report["bucket_count"] == 4
    assert report["validated_bar_count"] == 4
    assert report["duplicate_bucket_count"] == 0


def test_gap_statistics_are_informational_only():
    rows = [
        dict(row(0), bar_time="2026-11-02T15:30:00+00:00"),
        dict(row(0), bar_time="2026-11-02T15:31:00+00:00"),
        dict(row(0), bar_time="2026-11-02T15:35:00+00:00"),
    ]
    report = audit_candle_rows(rows)

    assert report["gaps"]["SPY"]["ONE_MINUTE"] == {
        "validated_bucket_count": 3,
        "largest_gap_seconds": 240,
    }
    assert any("do not establish missing bars" in caveat for caveat in CAVEATS)
    assert report["caveats"] == list(CAVEATS)


def test_summary_omits_raw_observations():
    report = audit_candle_rows([row(0), row(0, close=501.0)])
    summary = summarize_report(report)

    assert summary["conflicting_bucket_count"] == 1
    assert "buckets" not in summary
    assert "invalid_rows" not in summary
    json.dumps(summary)  # summary stays serialisable and low-volume


def test_datetime_timestamps_and_empty_input():
    assert audit_candle_rows([])["raw_row_count"] == 0

    aware = datetime(2026, 11, 2, 15, 30, 12, tzinfo=timezone.utc)
    report = audit_candle_rows([dict(row(0), bar_time=aware)])
    assert report["buckets"][0]["bar_time"] == "2026-11-02T15:30:00Z"
    assert report["validated_bar_count"] == 1


def test_non_sequence_input_is_rejected():
    with pytest.raises(TypeError):
        audit_candle_rows({"rows": []})
