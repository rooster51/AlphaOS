import pytest

from modules.public_observations import normalize_public_observations


def quote(updated_at="2030-01-02T14:30:00Z"):
    return {
        "symbol": "QQQ", "last": 500.0, "bid": 499.9, "ask": 500.1,
        "updated_at": updated_at,
    }


def chain(stamp="2030-01-02T14:29:30Z"):
    return {
        "symbol": "QQQ", "expiration": "2030-01-04",
        "calls": [{
            "contract": "QQQ-C500", "type": "Call", "strike": 500,
            "bid": 3.0, "ask": 3.2, "delta": .5,
            "bid_timestamp": stamp, "ask_timestamp": stamp,
        }],
        "puts": [{
            "contract": "QQQ-P500", "type": "Put", "strike": 500,
            "bid": 2.9, "ask": 3.1, "delta": -.5,
            "bid_timestamp": stamp, "ask_timestamp": stamp,
        }],
    }


def test_normalizes_public_snapshot_with_provenance_and_context():
    result = normalize_public_observations(
        "QQQ", "2030-01-04", quote(), chain(),
        observed_at="2030-01-02T14:30:30Z", max_quote_age_seconds=120,
    )
    assert result["fresh"] is True
    assert result["provider"] == "Public"
    assert result["market_research"]["spot"] == 500
    assert result["market_research"]["observation"]["fresh"] is True
    leg = result["chain"]["calls"][0]
    assert leg["symbol"] == "QQQ"
    assert leg["expiration"] == "2030-01-04"
    assert leg["quote_timestamp"] == "2030-01-02T14:29:30Z"


def test_stale_underlying_and_options_fail_closed():
    result = normalize_public_observations(
        "QQQ", "2030-01-04",
        quote("2030-01-02T14:20:00Z"),
        chain("2030-01-02T14:20:00Z"),
        observed_at="2030-01-02T14:30:30Z", max_quote_age_seconds=120,
    )
    assert result["fresh"] is False
    assert "stale_underlying_quote" in result["issues"]
    assert "stale_option_quotes" in result["issues"]
    assert result["market_research"]["observation"]["stale_contract_count"] == 2


def test_missing_timestamps_are_explicit_not_invented():
    q = quote(None)
    c = chain(None)
    result = normalize_public_observations(
        "QQQ", "2030-01-04", q, c,
        observed_at="2030-01-02T14:30:30Z",
    )
    assert result["fresh"] is False
    assert "missing_underlying_timestamp" in result["issues"]
    assert "missing_option_quote_timestamps" in result["issues"]
    assert result["market_research"]["observation"]["missing_contract_timestamp_count"] == 2
    assert result["chain"]["calls"][0]["quote_timestamp"] is None


@pytest.mark.parametrize("bad_quote,bad_chain", [
    ({"symbol": "SPY", "last": 500}, chain()),
    (quote(), {"symbol": "SPY", "expiration": "2030-01-04"}),
    (quote(), {"symbol": "QQQ", "expiration": "2030-01-05"}),
])
def test_context_mismatch_rejected(bad_quote, bad_chain):
    with pytest.raises(ValueError):
        normalize_public_observations(
            "QQQ", "2030-01-04", bad_quote, bad_chain,
            observed_at="2030-01-02T14:30:30Z",
        )


def test_future_timestamps_fail_closed():
    result = normalize_public_observations(
        "QQQ", "2030-01-04",
        quote("2030-01-02T14:31:00Z"),
        chain("2030-01-02T14:31:00Z"),
        observed_at="2030-01-02T14:30:30Z",
    )
    assert result["fresh"] is False
    assert "future_underlying_timestamp" in result["issues"]
    assert "future_option_quote_timestamp" in result["issues"]


def test_input_is_not_mutated():
    q, c = quote(), chain()
    original = dict(c["calls"][0])
    normalize_public_observations(
        "QQQ", "2030-01-04", q, c,
        observed_at="2030-01-02T14:30:30Z",
    )
    assert c["calls"][0] == original
    assert "quote_timestamp" not in c["calls"][0]


def test_stale_snapshot_gate_contract(monkeypatch):
    import modules.public_observations as module
    stale = normalize_public_observations(
        "QQQ", "2030-01-04", quote("2030-01-02T14:20:00Z"),
        chain("2030-01-02T14:20:00Z"),
        observed_at="2030-01-02T14:30:30Z", max_quote_age_seconds=120,
    )
    monkeypatch.setattr(module, "load_public_observations", lambda *args, **kwargs: stale)
    result = module.research_public_opportunities(
        "QQQ", "2030-01-04", observed_at="2030-01-02T14:30:30Z",
        opportunity_state={"direction": "bullish"},
    )
    assert result["status"] == "stale_or_incomplete_observations"
    assert result["candidates"] == []
    assert result["comparison"] is None


def test_fresh_snapshot_feeds_provider_free_session(monkeypatch):
    import modules.public_observations as module
    fresh = normalize_public_observations(
        "QQQ", "2030-01-04", quote(), chain(),
        observed_at="2030-01-02T14:30:30Z", max_quote_age_seconds=120,
    )
    monkeypatch.setattr(module, "load_public_observations", lambda *args, **kwargs: fresh)
    result = module.research_public_opportunities(
        "QQQ", "2030-01-04", observed_at="2030-01-02T14:30:30Z",
        opportunity_state={"direction": "bullish"},
    )
    assert result["provider_observation"]["fresh"] is True
    assert result["research_session"]["symbol"] == "QQQ"
    assert result["research_session"]["opportunity_state"]["direction"] == "bullish"
