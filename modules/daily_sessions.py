"""Exchange-session gating for the unattended runner, independent of the UI."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd


class SessionCalendar:
    def __init__(self):
        import pandas_market_calendars as mcal
        self.calendar=mcal.get_calendar('NYSE')

    def eligible_session(self,now,earliest_hour=17):
        if now.tzinfo is None: raise ValueError('An aware clock is required.')
        local=now.astimezone(ZoneInfo('America/New_York'))
        day=local.date().isoformat()
        schedule=self.calendar.schedule(start_date=day,end_date=day)
        if schedule.empty: return None,'non_trading_day'
        if local.hour<earliest_hour or pd.Timestamp(now)<schedule.market_close.iloc[0]:
            return None,'before_collection_window'
        return day,'completed_session'

    def sessions(self,start,end):
        return self.calendar.schedule(start_date=start,end_date=end).index
