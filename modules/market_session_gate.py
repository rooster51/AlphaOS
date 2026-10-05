"""NYSE regular-session gate and deterministic archive slots."""
from __future__ import annotations
from datetime import datetime, timezone
import pandas_market_calendars as mcal

def regular_session_slot(now=None, cadence_minutes=5):
    """Return a deterministic UTC slot only while NYSE regular trading is open."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    calendar = mcal.get_calendar("NYSE")
    schedule = calendar.schedule(start_date=now.date(), end_date=now.date())
    if schedule.empty:
        return None
    market_open = schedule.iloc[0]["market_open"].to_pydatetime()
    market_close = schedule.iloc[0]["market_close"].to_pydatetime()
    if not (market_open <= now < market_close):
        return None
    minute = (now.minute // cadence_minutes) * cadence_minutes
    return now.replace(minute=minute, second=0, microsecond=0)
