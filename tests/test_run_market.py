import pandas as pd

from modules.run_market import run_market
from tests.test_market_archive_adapter import payload


def history():
    days = pd.bdate_range("2029-09-01", "2030-01-01")
    return pd.DataFrame(dict(
        date=days, symbol="QQQ",
        open=range(100,100+len(days)), close=range(100,100+len(days)),
        high=range(101,101+len(days)), low=range(99,99+len(days)),
    ))


def test_run_qqq_archive_to_research_session_is_read_only_and_unranked():
    result = run_market(
        payload(), expiration="2030-01-02", history=history(),
        session_context={"open":"2030-01-02T14:30:00Z","close":"2030-01-02T21:00:00Z"},
        available_capital=500,
    )
    assert result["command"] == "Run QQQ"
    assert result["read_only"] is True
    assert result["status"] == "complete"
    session = result["research_session"]
    assert session["opportunity_state"]["direction"] == "bullish"
    assert session["opportunity_state"]["time_state"] == "late_0dte"
    assert session["candidates"]
    assert session["comparison"]["winner"] is None
    assert session["comparison"]["recommendation"] is None


def test_run_without_history_does_not_invent_direction():
    result = run_market(
        payload(), expiration="2030-01-02",
        session_context={"open":"2030-01-02T14:30:00Z","close":"2030-01-02T21:00:00Z"},
    )
    state = result["research_session"]["opportunity_state"]
    assert state["direction"] == "unknown"
    assert state["premium_state"] == "unknown"
    assert state["volatility_state"] == "unknown"
