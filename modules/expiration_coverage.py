"""Calendar labels and bounded collection policy; never synthesize expirations."""
from datetime import date, timedelta
from functools import lru_cache

from modules.research_calendar import nyse_schedule

HORIZONS = ('0dte', '1dte', 'weekly', 'monthly', 'long_dated')


@lru_cache(maxsize=16)
def _sessions(year):
    return frozenset(nyse_schedule(f'{year}-01-01', f'{year}-12-31').index.date)


def classify_expiration(session, expiration):
    day, expiry = date.fromisoformat(session), date.fromisoformat(expiration)
    if day.isoformat() != session or expiry.isoformat() != expiration:
        raise ValueError('ISO calendar dates required.')
    dte = (expiry-day).days
    sessions = _sessions(expiry.year)
    first = expiry.replace(day=1)
    third_friday = first + timedelta(days=(4-first.weekday()) % 7+14)
    monthly = max(d for d in sessions if first <= d <= third_friday)
    valid = dte >= 0 and expiry in sessions
    horizon = ('0dte' if dte == 0 else '1dte' if dte == 1 else
        'long_dated' if dte >= 365 else 'monthly' if expiry == monthly else
        'weekly' if 2 <= dte <= 7 else 'other')
    return dict(expiration=expiration, calendar_dte=dte, horizon=horizon,
        calendar_kind='standard_monthly_date' if expiry == monthly else 'other_listed_date',
        exchange_session=expiry in sessions, eligible_date=valid)


def select_expirations(expirations, session, config):
    """Keep the existing DTE window; optionally add one monthly and one >=1y.

    The provider must actually list each exact date. No nearest-expiry fallback
    and no presumption that a calendar date establishes provider entitlement.
    """
    extended = config.get('extended_expiration_coverage', False)
    if type(extended) is not bool:
        raise ValueError('extended_expiration_coverage must be boolean.')
    if not isinstance(expirations, list):
        raise ValueError('Provider expiration list required.')
    discovered, invalid = {}, 0
    for expiry in expirations:
        try:
            day = date.fromisoformat(expiry)
            if day.isoformat() != expiry:
                raise ValueError()
            context = classify_expiration(session, expiry) if extended else dict(calendar_dte=(day-date.fromisoformat(session)).days)
            if extended and not context['exchange_session']:
                raise ValueError()
            discovered[expiry] = context
        except (ValueError, TypeError):
            invalid += 1
    selected = {e for e, c in discovered.items() if config['min_dte'] <= c['calendar_dte'] <= config['max_dte']}
    if extended:
        for horizon in ('monthly', 'long_dated'):
            candidates = sorted(e for e, c in discovered.items()
                if e not in selected and c['eligible_date'] and c['horizon'] == horizon)
            if candidates:
                selected.add(candidates[0])
    return sorted(selected), dict(provider_expirations=sorted(discovered),
        invalid_expiration_count=invalid, excluded_expiration_count=len(discovered)-len(selected),
        extended_expiration_coverage=extended, additional_expiration_limit=2 if extended else 0)


def archive_coverage(options, session):
    """Describe stored observations, not quote freshness or research eligibility."""
    requested = options.get('requested_expirations') or []
    failed = {r.get('expiration') for r in options.get('expiration_failures', []) if isinstance(r, dict)}
    entries = []
    for expiry in sorted(set(requested)):
        try:
            context = classify_expiration(session, expiry)
        except (ValueError, TypeError):
            continue
        count = sum(isinstance(r, dict) and r.get('expiration') == expiry
            for bucket in ('valid_contracts', 'questionable_contracts') for r in options.get(bucket, []))
        present = context['eligible_date'] and expiry not in failed and count > 0
        entries.append(dict(context, observation_count=count,
            status='archived_observations' if present else 'missing_verified_evidence',
            reason=None if present else 'failed_empty_or_invalid_expiration'))
    return dict(version='expiration-coverage-v1', entries=entries,
        horizons={h: dict(status='archived_observations' if any(e['horizon'] == h and e['status'] == 'archived_observations' for e in entries)
            else 'missing_verified_evidence', expirations=[e['expiration'] for e in entries if e['horizon'] == h and e['status'] == 'archived_observations'])
            for h in HORIZONS},
        caveat='Calendar labels, not exchange series certification. Long-dated means >=365 calendar days, not verified LEAPS branding. Stored observations do not establish fresh executable quotes or candidate eligibility.')
