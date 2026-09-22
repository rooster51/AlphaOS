"""Public daily history adapter, including its supported dated long-history route."""
import re
import pandas as pd

from modules.history_diagnostics import HistoryError, history_diagnostics, schema_issues, api_error_detail
from modules.market_state import validate_ohlc

SUPPORTED_PERIODS = {'MONTH','YEAR','FIVE_YEARS','TEN_YEARS'}
ADJUSTMENT = ('Provider regularMarket open/high/low/close used together, unchanged. '
              'No adjusted-close substitution or synthetic adjustment. Public does not '
              'document split/dividend adjustment for these fields; unverified, not total return.')


def research_request(symbol, period, kind, as_of):
    if period not in SUPPORTED_PERIODS:
        raise ValueError('Unsupported research period. Daily MAX/ALL history is not verified.')
    if not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9 .^$-]{1,40}',symbol):
        raise ValueError('Invalid research symbol.')
    provider_period = 'SINCE_PURCHASE' if period == 'TEN_YEARS' else period
    start = (pd.Timestamp(as_of).normalize()-pd.DateOffset(years=10)).date().isoformat() if period=='TEN_YEARS' else None
    return (f'/userapigateway/historicdata/{kind}/{symbol}/{provider_period}/ONE_DAY',
            {'purchaseDate':start} if start else None, provider_period, start)


def validate_coverage(frame, symbol, period, as_of, diagnostic):
    """Fail closed for older equities: no shorter fallback, resampling or repair.

    Seven calendar days at each endpoint allow exchange closures, not missing
    years. Interior gaps >7 days or median spacing >3 reject coarse data.
    This is a gross-truncation guard, not an authoritative exchange calendar.
    """
    if period not in ('FIVE_YEARS','TEN_YEARS'):
        return
    diagnostic['stage'] = 'ohlc_validation'
    try:
        clean, audit = validate_ohlc(frame.assign(symbol=symbol),as_of)
    except ValueError as exc:
        raise HistoryError(str(exc),diagnostic) from None
    diagnostic['stage'] = 'coverage_validation'
    target = pd.Timestamp(as_of).normalize()-pd.DateOffset(years=10 if period=='TEN_YEARS' else 5)
    dates = clean.date
    if dates.iloc[0] > target + pd.Timedelta(days=7):
        raise HistoryError(f'Provider history starts {dates.iloc[0].date()}, later than the requested {target.date()} start; history is truncated or unavailable.',diagnostic)
    if dates.iloc[-1] < pd.Timestamp(as_of).normalize()-pd.Timedelta(days=7):
        raise HistoryError('Provider history ends more than seven calendar days before the request; history is stale or truncated.',diagnostic)
    spacing = dates.diff().dt.days.dropna()
    if spacing.empty or spacing.median()>3 or spacing.max()>7:
        raise HistoryError('Provider history is sparse or not daily; requested daily coverage was not supplied.',diagnostic)
    diagnostic.update(completed_rows=len(clean),excluded_uncompleted=audit['excluded_uncompleted'],
                      first_completed_date=str(dates.iloc[0].date()),last_completed_date=str(dates.iloc[-1].date()),
                      max_calendar_gap_days=audit['max_calendar_gap_days'],calendar_verified=False)


def fetch_research_bars(client, symbol, period, kind='EQUITY', as_of=None):
    """SDK authenticated transport and BarsResponse schema; inspect before parsing.

    TEN_YEARS/ONE_DAY is rejected by Public with HTTP 400. SINCE_PURCHASE
    with purchaseDate is a documented start-date query, not an account holding
    import. It returns actual daily OHLC up to now without chunking or fill.
    """
    from public_api_sdk.models.historic_data import BarsResponse
    from pydantic import ValidationError as SchemaError
    as_of = as_of or pd.Timestamp.now(tz='America/New_York').date()
    path, params, provider_period, start = research_request(symbol,period,kind,as_of)
    diagnostic = history_diagnostics(symbol,period)
    diagnostic.update(provider_period=provider_period,requested_start=start,
                      requested_end=str(pd.Timestamp(as_of).date()),adjustment=ADJUSTMENT,
                      retrieved_at=pd.Timestamp.now(tz='UTC').isoformat())
    try:
        client.auth_manager.refresh_token_if_needed()
        raw = client.api_client.get(path,params=params)
    except Exception as exc:
        status = getattr(exc,'status_code',None)
        diagnostic.update(http_status=status if isinstance(status,int) else None,
                          provider_reason_terms=api_error_detail(exc))
        reason = ('Public rejected the requested period/aggregation (HTTP 400); no shorter history was substituted.' if status==400
                  else 'Public history request failed; verify access or retry later.')
        raise HistoryError(reason,diagnostic) from None
    diagnostic['stage'] = 'provider_schema'
    if not isinstance(raw,dict):
        raise HistoryError('Unexpected provider response schema: expected a history object.',diagnostic)
    regular = raw.get('regularMarket')
    bars = regular.get('bars') if isinstance(regular,dict) else None
    if isinstance(bars,list) and all(isinstance(bar,dict) for bar in bars):
        frame = pd.DataFrame([{key:bar.get('timestamp' if key=='date' else key)
            for key in ('date','open','high','low','close','volume')} for bar in bars])
        diagnostic.update({k:v for k,v in history_diagnostics(symbol,period,frame).items() if k!='stage'})
    try:
        response = BarsResponse(**raw)
    except SchemaError as exc:
        diagnostic['schema_issues'] = schema_issues(exc)
        raise HistoryError('Unexpected provider response schema; see the field-level diagnostic.',diagnostic) from None
    if response.symbol != symbol or response.period != provider_period:
        raise HistoryError('Provider response symbol or period does not match the request.',diagnostic)
    if raw.get('leadingFill'):
        raise HistoryError('Provider supplied a synthetic leading-fill descriptor; full observed history is unavailable.',diagnostic)
    result = pd.DataFrame([dict(date=bar.timestamp,open=float(bar.open),high=float(bar.high),
        low=float(bar.low),close=float(bar.close),volume=float(bar.volume)) for bar in response.regular_market.bars],
        columns=['date','open','high','low','close','volume'])
    diagnostic['regular_expected_bars'] = response.regular_market.expected_bars
    diagnostic['stage'] = 'normalization'
    if result.empty:
        raise HistoryError('Public returned no regular-market daily bars.',diagnostic)
    if kind=='EQUITY':
        validate_coverage(result,symbol,period,as_of,diagnostic)
    result.attrs['provider_diagnostics'] = dict(diagnostic,stage='validated')
    return result
