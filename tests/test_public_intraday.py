from types import SimpleNamespace

import pytest

from modules.public_intraday import fetch_intraday_bars


class _Client:
    def __init__(self, symbol, bars):
        self.symbol = symbol
        self.bars = bars
        self.call = None

    def get_bars(self, symbol, period, aggregation=None):
        self.call = (symbol, period, aggregation)
        return SimpleNamespace(
            symbol=self.symbol,
            regular_market=SimpleNamespace(bars=self.bars),
        )


class _Provider:
    def __init__(self, symbol, bars):
        self.client = _Client(symbol, bars)


def _bar(**overrides):
    values = dict(
        timestamp="2026-10-02T13:30:00+00:00",
        open=600,
        high=601,
        low=599,
        close=600.5,
        volume=12345,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_one_minute_public_sdk_normalization():
    provider = _Provider("QQQ", [_bar()])
    rows = fetch_intraday_bars(provider, "QQQ", "ONE_MINUTE")

    assert provider.client.call is not None
    symbol, period, aggregation = provider.client.call
    assert symbol == "QQQ"
    assert getattr(period, "name", None) == "DAY" or getattr(period, "value", None) == "DAY"
    assert getattr(aggregation, "name", None) == "ONE_MINUTE" or getattr(aggregation, "value", None) == "ONE_MINUTE"
    assert len(rows) == 1
    assert rows[0]["symbol"] == "QQQ"
    assert rows[0]["aggregation"] == "ONE_MINUTE"
    assert rows[0]["close"] == 600.5
    assert rows[0]["volume"] == 12345.0


def test_incomplete_bar_is_not_fabricated():
    provider = _Provider("SPY", [_bar(close=None)])
    with pytest.raises(RuntimeError, match="no complete regular-market intraday bars"):
        fetch_intraday_bars(provider, "SPY", "ONE_MINUTE")
