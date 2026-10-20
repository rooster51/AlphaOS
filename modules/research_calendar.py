"""Bounded reuse of package-defined NYSE schedules, never market observations."""
from functools import lru_cache
from threading import RLock
import pandas_market_calendars as mcal

_lock = RLock()


@lru_cache(maxsize=128)
def _schedule(start, end):
    return mcal.get_calendar('NYSE').schedule(start_date=start, end_date=end)


def nyse_schedule(start, end):
    # Serialize cache misses too: lru_cache alone can duplicate expensive cold
    # work. Return a copy so callers cannot corrupt another request's calendar.
    with _lock:
        return _schedule(str(start), str(end)).copy(deep=True)
