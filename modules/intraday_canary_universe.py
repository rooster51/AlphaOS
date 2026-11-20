"""Explicitly gated canary universe for the intraday archive.

This module does not enable collection by itself. The existing scheduled
collector remains limited to SPY/QQQ until a reviewed integration enables it.
"""

CORE_SYMBOLS = ("SPY", "QQQ")
CANARY_SYMBOLS = ("NVDA", "IWM")


def collection_symbols(config, canary=None):
    """Return a bounded symbol universe; never broaden defaults implicitly."""
    if not isinstance(config, dict) or config.get("symbols") != list(CORE_SYMBOLS):
        raise ValueError("Frozen SPY/QQQ baseline required for canary collection.")
    if canary in (None, "", "none"):
        return list(CORE_SYMBOLS)
    if not isinstance(canary, str) or canary not in CANARY_SYMBOLS:
        raise ValueError("Unsupported canary symbol.")
    return [*CORE_SYMBOLS, canary]
