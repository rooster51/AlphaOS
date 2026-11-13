from types import SimpleNamespace

import pytest

from modules.public_intraday import PublicIntradayError, fetch_intraday_bars


class _Client:
    def __init__(self, symbol, bars, *, regular=True):
        self.symbol = symbol
        self.bars = bars
        self.regular = regular
        self.call = None

    def get_bars(self, symbol, period, aggregation=None):
        self.call = (symbol, period, aggregation)
        return SimpleNamespace(
            symbol=self.symbol,
            regular_market=SimpleNamespace(bars=self.bars) if self.regular else None,
        )


class _Provider:
    def __init__(self, symbol, bars, *, regular=True):
        self.client = _Client(symbol, bars, regular=regular)


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
    assert rows[0]["timestamp"] == "2026-10-02T13:30:00+00:00"
    assert rows[0]["close"] == 600.5
    assert rows[0]["volume"] == 12345.0


def test_incomplete_bar_is_not_fabricated():
    provider = _Provider("SPY", [_bar(close=None)])
    with pytest.raises(PublicIntradayError) as caught:
        fetch_intraday_bars(provider, "SPY", "ONE_MINUTE")
    assert caught.value.code == "provider_bars_ohlc_missing"


@pytest.mark.parametrize(
    "timestamp,code",
    [
        ("2026-10-02T13:30:00", "provider_bars_timestamp_naive"),
        ("1762961400000", "provider_bars_timestamp_epoch_string"),
        ("2026-10-02", "provider_bars_timestamp_date_only"),
        ("not-a-timestamp", "provider_bars_timestamp_invalid"),
    ],
)
def test_timestamp_shapes_are_reported_without_values(timestamp, code):
    provider = _Provider("SPY", [_bar(timestamp=timestamp)])
    with pytest.raises(PublicIntradayError) as caught:
        fetch_intraday_bars(provider, "SPY", "ONE_MINUTE")
    assert caught.value.code == code
    assert timestamp not in str(caught.value)


def test_missing_regular_market_is_a_safe_provider_shape_error():
    provider = _Provider("SPY", [_bar()], regular=False)
    with pytest.raises(PublicIntradayError) as caught:
        fetch_intraday_bars(provider, "SPY", "ONE_MINUTE")
    assert caught.value.code == "provider_bars_regular_market_missing"


def test_empty_regular_market_is_not_treated_as_a_candle_set():
    provider = _Provider("SPY", [])
    with pytest.raises(PublicIntradayError) as caught:
        fetch_intraday_bars(provider, "SPY", "ONE_MINUTE")
    assert caught.value.code == "provider_bars_empty"


def test_provider_symbol_mismatch_is_not_relabelled():
    provider = _Provider("QQQ", [_bar()])
    with pytest.raises(PublicIntradayError) as caught:
        fetch_intraday_bars(provider, "SPY", "ONE_MINUTE")
    assert caught.value.code == "provider_bars_symbol_mismatch"
