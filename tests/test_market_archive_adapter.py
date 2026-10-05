from modules.market_archive_adapter import normalize_archive_snapshot
from modules.opportunity_session import research_market_opportunities


def payload():
    observed = "2030-01-02T20:30:00+00:00"
    rows = [
        dict(contract="QQQ300102C00500000", symbol="QQQ", expiration="2030-01-02", type="call",
             strike=500, bid=2.0, ask=2.2, delta=.5, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
        dict(contract="QQQ300102C00505000", symbol="QQQ", expiration="2030-01-02", type="call",
             strike=505, bid=.8, ask=1.0, delta=.2, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
        dict(contract="QQQ300102P00495000", symbol="QQQ", expiration="2030-01-02", type="put",
             strike=495, bid=.35, ask=.40, delta=-.2, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
        dict(contract="QQQ300102P00490000", symbol="QQQ", expiration="2030-01-02", type="put",
             strike=490, bid=.10, ask=.15, delta=-.1, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
    ]
    return {
        "schema_version": "intraday-archive-v1", "provider": "Public", "symbol": "QQQ",
        "session": "2030-01-02", "observed_at": observed,
        "underlying": {"last": 500, "last_timestamp": observed},
        "options": {"schema_version": "options-archive-v1", "symbol": "QQQ",
            "snapshot_date": "2030-01-02", "status": "complete",
            "quote_timing": "last_available_not_guaranteed_close",
            "requested_expirations": ["2030-01-02"], "expiration_failures": [],
            "valid_contracts": rows, "questionable_contracts": [], "rejected_contracts": []},
    }


def test_archive_adapter_normalizes_one_expiration_without_interpretation():
    result = normalize_archive_snapshot(payload(), "2030-01-02")
    assert result["symbol"] == "QQQ"
    assert result["market_research"]["spot"] == 500
    assert len(result["chain"]["calls"]) == 2
    assert len(result["chain"]["puts"]) == 2
    assert result["chain"]["puts"][0]["type"] == "Put"
    assert result["market_research"].get("opportunity_state") is None


def test_archive_snapshot_can_drive_existing_opportunity_session():
    archived = normalize_archive_snapshot(payload(), "2030-01-02")
    market = dict(archived["market_research"],
                  opportunity_state={"direction": "bullish", "premium_state": "rich",
                                     "movement_state": "breakout", "time_state": "late_0dte"})
    result = research_market_opportunities(
        "QQQ", market, archived["chain"], as_of=archived["observed_at"],
        expiration=archived["expiration"], available_capital=500, width=5,
    )
    families = {x["strategy_family"] for x in result["candidates"]}
    assert "call_debit_spread" in families
    assert "put_credit_spread" in families
    assert result["comparison"]["winner"] is None
    assert result["comparison"]["recommendation"] is None
