"""Bounded reuse of package-defined NYSE schedules, never market observations."""
from functools import lru_cache
from threading import RLock
import pandas_market_calendars as mcal
from modules.research_control import checkpoint

_lock = RLock()


@lru_cache(maxsize=128)
def _schedule(start, end):
    return _calendar().schedule(start_date=start, end_date=end)


@lru_cache(maxsize=1)
def _calendar():
    # Calendar rules are static package data. Reuse its expensive holiday cache
    # across different date ranges, under the same lock; never cache quotes.
    return mcal.get_calendar('NYSE')


def nyse_schedule(start, end):
    # Serialize cache misses too: lru_cache alone can duplicate expensive cold
    # work. Return a copy so callers cannot corrupt another request's calendar.
    checkpoint()
    with _lock:
        checkpoint()
        result = _schedule(str(start), str(end)).copy(deep=True)
    checkpoint()
    return result
