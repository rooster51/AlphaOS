"""Explicitly gated canary universe for the intraday archive.

This module does not enable collection by itself. The existing scheduled
collector remains limited to SPY/QQQ until a reviewed integration enables it.
"""

CORE_SYMBOLS = ("SPY", "QQQ")
from pathlib import Path
import json
import re


def archive_universe():
    """Repository-reviewed capabilities; listing a symbol never enables it."""
    config = json.loads((Path(__file__).resolve().parents[1] / 'config/archive_universe.json').read_text())
    optional = config.get('optional_symbols')
    limit = config.get('max_additional_symbols_per_run')
    if (not isinstance(optional, list) or not optional
            or any(not isinstance(s, str) or not re.fullmatch(r'[A-Z]{1,6}', s) for s in optional)
            or len(set(optional)) != len(optional) or set(optional).intersection(CORE_SYMBOLS)
            or type(limit) is not int or not 1 <= limit <= len(optional)):
        raise ValueError('Invalid reviewed archive universe.')
    return tuple(optional), limit


def enabled_archive_symbols(additional_symbols=()):
    optional, limit = archive_universe()
    if (not isinstance(additional_symbols, (tuple, list))
            or any(not isinstance(s, str) or s not in optional for s in additional_symbols)
            or len(set(additional_symbols)) != len(additional_symbols)
            or len(additional_symbols) > limit):
        raise ValueError('Unsupported or ambiguous additional archive symbols.')
    return [*CORE_SYMBOLS, *additional_symbols]


def collection_symbols(config, canary=None, additional=None):
    """Return a bounded symbol universe; never broaden defaults implicitly."""
    if not isinstance(config, dict) or config.get("symbols") != list(CORE_SYMBOLS):
        raise ValueError("Frozen SPY/QQQ baseline required for canary collection.")
    if additional not in (None, '', 'none'):
        if canary not in (None, '', 'none') or not isinstance(additional, str):
            raise ValueError('Choose one explicit collection opt-in configuration.')
        return enabled_archive_symbols([s.strip() for s in additional.split(',')])
    if canary in (None, "", "none"):
        return list(CORE_SYMBOLS)
    optional, _ = archive_universe()
    if not isinstance(canary, str) or canary not in optional:
        raise ValueError("Unsupported canary symbol.")
    return [*CORE_SYMBOLS, canary]
