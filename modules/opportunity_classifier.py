"""Conservative, descriptive classification from existing completed daily features."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from modules.opportunity_router import opportunity_state
from modules.structure_research import _number

VERSION = 'opportunity-classifier-v1'
LATE_0DTE_MINUTES = 60  # Configurable research convention, not an exchange rule.
NY = ZoneInfo('America/New_York')


def aware_time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp if stamp.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def classify_opportunity(evidence=None, *, observed_at=None, expiration=None,
                         session=None, late_minutes=LATE_0DTE_MINUTES):
    evidence = evidence or {}
    values = {k: 'unknown' for k in ('direction', 'premium_state', 'movement_state', 'time_state', 'volatility_state')}
    details = {k: dict(observations={}, rule='No established AlphaOS classification rule with sufficient evidence.',
                       conflicts=[], unavailable=['validated classification evidence']) for k in values}
    now = aware_time(observed_at)
    row = evidence.get('latest', {})
    valid = False
    try:
        valid = now is not None and date.fromisoformat(str(row.get('date'))[:10]) < now.astimezone(NY).date()
    except ValueError:
        pass
    if valid:
        nums = [_number(row.get(k)) for k in ('close', 'ema_9', 'ema_21', 'ema_50')]
        direction = 'unknown'
        if all(x is not None and x > 0 for x in nums):
            if all(a > b for a, b in zip(nums, nums[1:])): direction = 'bullish'
            elif all(a < b for a, b in zip(nums, nums[1:])): direction = 'bearish'
        previous = evidence.get('previous', {})
        breakout = None
        try:
            prior_valid = date.fromisoformat(str(previous.get('date'))[:10]) < date.fromisoformat(str(row['date'])[:10])
        except ValueError:
            prior_valid = False
        hi, lo, close = _number(previous.get('high_20')), _number(previous.get('low_20')), nums[0]
        if prior_valid and all(x is not None and x > 0 for x in (hi, lo, close)) and hi > lo:
            breakout = 'bullish' if close > hi else 'bearish' if close < lo else None
        conflicts = [direction, breakout] if breakout and direction != 'unknown' and direction != breakout else []
        values['direction'] = 'unknown' if conflicts else direction
        values['movement_state'] = 'unknown' if conflicts else 'breakout' if breakout else 'directional' if direction != 'unknown' else 'unknown'
        for key in ('direction', 'movement_state'):
            details[key] = dict(observations={'latest': row, 'previous': previous},
                rule='Existing strict close/EMA9/EMA21/EMA50 ordering; mixed is unknown. Completed close outside prior 20-session high/low is breakout and supersedes directional; opposing signs are unknown.',
                conflicts=conflicts, unavailable=[] if values[key] != 'unknown' else ['consistent directional evidence'])
    for key in ('premium_state', 'volatility_state'):
        details[key]['observations'] = evidence.get('volatility', {})
        details[key]['rule'] = 'IV, realized volatility and forward distributions alone have no calibrated regime/richness rule in this branch; remain unknown.'
    session = session or {}
    opened, closed = aware_time(session.get('open')), aware_time(session.get('close'))
    if not isinstance(late_minutes, (int, float)) or isinstance(late_minutes, bool) or not 0 < late_minutes <= 390:
        raise ValueError('late_minutes must be in (0, 390].')
    try:
        expiry = date.fromisoformat(str(expiration))
    except ValueError:
        expiry = None
    if (now and opened and closed and opened <= now < closed and
            opened.astimezone(NY).date() == closed.astimezone(NY).date() == now.astimezone(NY).date()
            and expiry is not None and expiry >= now.astimezone(NY).date()):
        values['time_state'] = 'late_0dte' if expiry == now.astimezone(NY).date() and (closed-now).total_seconds() <= late_minutes*60 else 'standard'
        details['time_state'] = dict(observations=dict(observed_at=observed_at, expiration=expiration, session=session, late_minutes=late_minutes),
            rule='Inside explicit exchange session; same-day expiry within configured minutes of close is late_0dte. Outside session remains unknown.', conflicts=[], unavailable=[])
    state = opportunity_state(**values, evidence=details, caveats=[
        'Descriptive completed-session evidence, not trade confidence or a recommendation.',
        'Range-bound, large-move and pin classifications lack established rules and remain unknown.',
        'Session bounds must be supplied from an authoritative calendar, including early closes.',
        'Daily trend is lagged; no inference of current intraday trend or premium attractiveness.'])
    state['classifier_version'] = VERSION
    return state


def history_evidence(history, symbol, observed_at):
    from modules.market_state import validate_ohlc, market_state_features
    now = aware_time(observed_at)
    if now is None:
        raise ValueError('Timezone-aware research timestamp required.')
    clean, audit = validate_ohlc(history, now.astimezone(NY).date())
    if clean.symbol.iloc[0] != symbol:
        raise ValueError('History symbol mismatch.')
    features = market_state_features(clean, now.astimezone(NY).date())
    def row(index):
        item = features.iloc[index]
        return dict(date=str(item.date.date()), **{k: _number(item.get(k)) for k in
            ('close', 'ema_9', 'ema_21', 'ema_50', 'high_20', 'low_20', 'realized_vol_20d', 'realized_vol_60d')})
    latest = row(-1)
    return dict(latest=latest, previous=row(-2) if len(features)>1 else {}, audit=audit,
                volatility={k: latest[k] for k in ('realized_vol_20d', 'realized_vol_60d')})


def expected_move_context(value, horizon, observed_at, expiration):
    now = aware_time(observed_at)
    horizon = horizon or {}
    start, end = aware_time(horizon.get('start')), aware_time(horizon.get('end'))
    amount = _number(value)
    matched = bool(now and start == now and end and end > now and
                   end.astimezone(NY).date().isoformat() == str(expiration) and amount is not None and amount >= 0)
    return dict(value=value, horizon=horizon, comparison_available=matched,
                reason='explicit_matching_interval' if matched else 'unknown_or_mismatched_horizon'), amount if matched else None
