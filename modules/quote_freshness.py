"""Shared observation quality. Retrieval time never replaces observation time."""
from datetime import datetime, timezone, timedelta
from functools import lru_cache
import math
import os
from zoneinfo import ZoneInfo
import pandas as pd

NY = ZoneInfo('America/New_York')


def normalize_timestamp(value):
    """Preserve aware instants; reject naive timestamps and unsupported epoch units."""
    try:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                return None
            unit = 'ms' if 1e12 <= value < 1e13 else 's' if 1e9 <= value < 1e10 else None
            if unit is None:
                return None
            stamp = pd.Timestamp(value, unit=unit, tz='UTC')
        else:
            stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            return None
        return stamp.tz_convert('UTC').isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


@lru_cache(maxsize=32)
def session_schedule(day):
    import pandas_market_calendars as mcal
    return mcal.get_calendar('NYSE').schedule(start_date=day-timedelta(days=14), end_date=day)


def market_state(now):
    """Exchange holidays/early closes; 04-20 ET extended policy, no ATS entitlement claim."""
    try:
        local = now.astimezone(NY)
        schedule = session_schedule(local.date())
        today = schedule[schedule.index.date == local.date()]
        if not today.empty:
            opening, closing = today.iloc[0][['market_open', 'market_close']]
            if opening <= now < closing:
                return 'regular_open', None
            if 4 <= local.hour < 20:
                return 'extended_hours', None
        completed = schedule[schedule.market_close <= now]
        close = completed.market_close.iloc[-1].to_pydatetime() if not completed.empty else None
        return 'closed', close
    except Exception:
        return 'unknown', None


def configured_limit(name, default, ceiling):
    try:
        value = float(os.environ.get(name, default))
        return value if math.isfinite(value) and 0 < value <= ceiling else default
    except ValueError:
        return default


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def quote_quality(quote):
    bid, ask = quote.get('bid'), quote.get('ask')
    limit = configured_limit('ALPHAOS_MAX_UNDERLYING_SPREAD_PCT', 0.5, 5.0)
    spread = ask-bid if positive(bid) and positive(ask) else None
    pct = spread / ((bid+ask)/2) * 100 if spread is not None else None
    if bid is None or ask is None:
        reason = 'missing_bid_or_ask'
    elif not positive(bid) or not positive(ask):
        reason = 'nonpositive_or_nonfinite_bid_or_ask'
    elif ask < bid:
        reason = 'crossed_market'
    elif pct > limit:
        reason = 'abnormally_wide_spread'
    else:
        reason = 'within_spread_limit'
    return dict(last_price_valid=positive(quote.get('last')), bid_ask_valid=reason == 'within_spread_limit',
        bid_ask_reason=reason, bid_ask_quality='acceptable' if reason == 'within_spread_limit' else 'suspect',
        bid_ask_spread=spread, bid_ask_spread_pct=pct, max_bid_ask_spread_pct=limit,
        bid_ask_timestamp_verified=False)


def freshness(quote, now=None, retrieved_at=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Freshness clock must be timezone-aware')
    stamp = normalize_timestamp(quote.get('updated_at'))
    retrieval = normalize_timestamp(retrieved_at or quote.get('retrieved_at'))
    age = (now-pd.Timestamp(stamp).to_pydatetime()).total_seconds() if stamp else None
    cache_age = (now-pd.Timestamp(retrieval).to_pydatetime()).total_seconds() if retrieval else None
    session, close = market_state(now)
    limit = configured_limit('ALPHAOS_MAX_QUOTE_AGE_SECONDS', 120., 900.)
    status, reason = 'unknown', 'missing_or_ambiguous_timestamp'
    if age is not None:
        if age < -60:
            reason = 'future_timestamp'
        elif session in ('regular_open', 'extended_hours'):
            status = 'fresh' if age <= limit else 'stale'
            reason = 'within_active_age_limit' if status == 'fresh' else 'active_quote_too_old'
        elif session == 'closed' and close is not None:
            recent_close = pd.Timestamp(stamp) >= pd.Timestamp(close)-pd.Timedelta(seconds=limit)
            status = 'latest_available' if recent_close else 'stale'
            reason = 'latest_completed_session_observation' if recent_close else 'predates_latest_session_close'
        else:
            reason = 'market_schedule_unavailable'
    quality = quote_quality(quote)
    live = status == 'fresh' and quality['last_price_valid']
    return dict(quote_as_of=stamp, quote_timezone='UTC' if stamp else None, retrieved_at=retrieval,
        evaluated_at=now.astimezone(timezone.utc).isoformat(), age_seconds=age, cache_age_seconds=cache_age,
        source='Public', market_state=session,
        market_state_source='NYSE calendar; 04:00-20:00 ET extended policy; overnight ATS status unverified',
        data_status=status, freshness=status, freshness_reason=reason, max_age_seconds=limit,
        usable_for_live_research=live,
        usable_for_contextual_research=status in ('fresh', 'latest_available') and quality['last_price_valid'],
        usable_for_execution_analysis=live and quality['bid_ask_valid'],
        execution_analysis_scope='Underlying quote sanity only; bid/ask timestamps, entitlement and executable fills unverified',
        observation_context='dated_closed_market_observation' if session == 'closed' else 'active_session_observation' if session != 'unknown' else 'unknown',
        real_time_entitlement_verified=False, quote_quality=quality)


class QuoteUnavailable(ValueError):
    """Safe user-facing reason; contains no provider response or credentials."""


def require_research_quote(quote, now=None, retrieved_at=None, *, live=True):
    result = freshness(quote, now, retrieved_at)
    if not result['usable_for_live_research' if live else 'usable_for_contextual_research']:
        raise QuoteUnavailable('Public quote is not usable for new live research (stale, unknown or market closed). '
            'Refresh during an active session, or use explicit inputs for non-live historical research.')
    return result
