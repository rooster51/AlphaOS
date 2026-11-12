"""Offline tests for the private authenticated candle display probe."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.candle_display_probe import (
    HttpResponse,
    analyze_snapshot,
    main,
    probe_pair,
)

NOW = datetime(2026, 11, 10, 15, 5, tzinfo=timezone.utc)


def snapshot(*, interval="1m", times=None, retrieved_at="2026-11-10T15:04:00Z"):
    times = times or [
        "2026-11-10T15:00:00Z",
        "2026-11-10T15:01:00Z",
        "2026-11-10T15:03:00Z",
    ]
    return {
        "schema_version": "alphaos-candles-v1",
        "symbol": "SPY",
        "interval": interval,
        "provider": "Public",
        "session": "regular",
        "retrieved_at": retrieved_at,
        "latest_candle_at": times[-1],
        "snapshot_id": "a" * 64,
        "expected_bars": 390,
        "received_bars": len(times),
        "returned_bars": len(times),
        "completeness": "incomplete",
        "last_bar_status": "complete",
        "freshness": "fresh",
        "warnings": ["missing_bars"],
        "candles": [
            {
                "time": stamp,
                "open": 600.0,
                "high": 601.0,
                "low": 599.0,
                "close": 600.5,
                "volume": 10_000,
            }
            for stamp in times
        ],
        "provider_capabilities": {
            "provider": "Public",
            "symbols": ["SPY", "QQQ"],
            "intervals": ["1m", "5m", "15m"],
            "sessions": ["regular"],
            "latest_quotes": True,
            "native_candles": True,
            "provider_native_intervals": True,
            "expected_bar_metadata": True,
            "entitlement": {},
        },
        "entitlement": {
            "provider": "Public",
            "use_context": "owner_private_display",
            "allowed": True,
            "code": "allowed",
            "reason": "Synthetic test fixture.",
            "basis": "Test only.",
            "policy_version": "alphaos-data-use-v1",
            "authorization_required": False,
            "authorization_reference_present": False,
        },
    }


def body(value):
    return json.dumps(value).encode("utf-8")


def test_snapshot_measurements_include_age_gap_and_timestamp_consistency():
    result = analyze_snapshot(snapshot(), symbol="SPY", interval="1m", now=NOW)
    assert result["status"] == "valid"
    assert result["data_age_seconds"] == 120
    assert result["snapshot_age_seconds"] == 60
    assert result["coverage"]["missing_bars"] == 1
    assert result["timestamps"] == {
        "strictly_increasing": True,
        "interval_aligned": True,
        "latest_matches_last_bar": True,
        "retrieved_after_latest": True,
        "bars_valid": True,
        "counts_valid": True,
    }


def test_probe_requires_owner_private_display_not_private_research():
    value = snapshot()
    value["entitlement"]["use_context"] = "private_research"
    result = analyze_snapshot(value, symbol="SPY", interval="1m", now=NOW)
    assert result["status"] == "invalid"
    assert result["entitlement"]["use_context"] == "private_research"


def test_misaligned_or_retrieved_before_latest_is_invalid():
    misaligned = analyze_snapshot(
        snapshot(times=["2026-11-10T15:00:00Z", "2026-11-10T15:01:30Z"]),
        symbol="SPY",
        interval="1m",
        now=NOW,
    )
    assert misaligned["status"] == "invalid"
    assert misaligned["timestamps"]["interval_aligned"] is False

    early = analyze_snapshot(
        snapshot(retrieved_at="2026-11-10T15:02:00Z"),
        symbol="SPY",
        interval="1m",
        now=NOW,
    )
    assert early["status"] == "invalid"
    assert early["timestamps"]["retrieved_after_latest"] is False


def test_probe_reports_feature_disabled_without_fabricating_data():
    def transport(url, session):
        assert session == "session-value"
        assert "__Host-alphaos_session" not in url
        return HttpResponse(
            503,
            {"cache-control": "private, no-store"},
            body({"status": "unavailable", "code": "feature_disabled"}),
        )

    result = probe_pair(transport, "https://alphaos.test", "session-value", "SPY", "1m", now=NOW)
    assert result["available"] is False
    assert result["status"] == "blocked"
    assert result["error"] == "feature_disabled"
    assert "data_age_seconds" not in result


def test_probe_measures_candle_and_quote_through_the_website_path():
    def transport(url, session):
        assert session == "session-value"
        if "/api/candles/SPY?" in url:
            return HttpResponse(200, {"cache-control": "private, no-store"}, body({
                "status": "ok",
                "snapshot": snapshot(),
            }))
        if "/api/current-quote?symbol=SPY" in url:
            return HttpResponse(200, {"cache-control": "private, no-store"}, body({
                "status": "fresh",
                "lastAt": "2026-11-10T15:04:30Z",
                "retrievedAt": "2026-11-10T15:04:31Z",
                "ageSeconds": 29,
            }))
        raise AssertionError(f"unexpected URL: {url}")

    result = probe_pair(transport, "https://alphaos.test", "session-value", "SPY", "1m", now=NOW)
    assert result["status"] == "valid"
    assert result["quote"]["status"] == "fresh"
    assert result["quote"]["age_seconds"] == 29
    assert result["coverage"]["missing_bars"] == 1


def test_probe_requires_both_environment_values_and_never_prints_the_session(
    monkeypatch, capsys,
):
    monkeypatch.setenv("ALPHAOS_SITE_URL", "https://alphaos.test")
    monkeypatch.setenv("ALPHAOS_WEBSITE_SESSION", "super-secret-session")
    monkeypatch.delenv("ALPHAOS_WEBSITE_SESSION")
    called = False

    def transport(url, session):
        nonlocal called
        called = True
        raise AssertionError("network must not be attempted")

    assert main([], transport=transport, now=NOW) == 2
    output = capsys.readouterr().out
    assert "configuration_missing" in output
    assert "super-secret-session" not in output
    assert called is False
