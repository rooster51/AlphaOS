from modules.intraday_canary_universe import collection_symbols


def test_default_symbols_unchanged():
    assert collection_symbols({'symbols': ['SPY', 'QQQ']}) == ['SPY', 'QQQ']


def test_explicit_canary():
    assert collection_symbols({'symbols': ['SPY', 'QQQ']}, 'NVDA') == ['SPY', 'QQQ', 'NVDA']
