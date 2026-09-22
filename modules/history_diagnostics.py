"""Allowlisted research diagnostics. Never serialize provider errors or inputs."""
import numpy as np
import pandas as pd
import re


def api_error_detail(exc):
    """Only fixed vocabulary can leave the server, never arbitrary error text."""
    allowed = set('invalid unsupported not supported period aggregation combination enum value request parameter parameters argument type failed convert conversion allowed values must be one of is for to from string no data available range maximum exceeded too many bars bad FIVE_YEARS TEN_YEARS ALL SINCE_PURCHASE ONE_DAY ONE_WEEK ONE_MONTH EQUITY'.lower().split())
    message = getattr(exc,'message','')
    if not isinstance(message,str):
        return []
    return [word.lower() for word in re.findall(r'[A-Za-z_]+',message) if word.lower() in allowed][:60]


class HistoryError(ValueError):
    def __init__(self, reason, diagnostics):
        self.diagnostics = dict(diagnostics)
        self.diagnostics['reason'] = reason
        super().__init__(f"{diagnostics['symbol']} {diagnostics['requested_period']}: {reason}")


def history_diagnostics(symbol, period, history=None):
    result = dict(symbol=symbol, requested_period=period, provider='Public',
                  aggregation='ONE_DAY', returned_rows=None, first_date=None, last_date=None,
                  stage='provider_request')
    if history is None:
        return result
    result['returned_rows'] = len(history)
    if 'date' in history:
        dates = pd.to_datetime(history.date, utc=True, errors='coerce', format='mixed').dt.tz_convert(None).dt.normalize()
        valid = dates.dropna()
        result.update(first_date=str(valid.min().date()) if len(valid) else None,
                      last_date=str(valid.max().date()) if len(valid) else None,
                      invalid_dates=int(dates.isna().sum()),
                      duplicate_dates=int(dates.duplicated().sum()),
                      weekend_rows=int((dates.dt.dayofweek >= 5).sum()))
    cols = ['open', 'high', 'low', 'close']
    if set(cols).issubset(history):
        prices = history[cols].apply(pd.to_numeric, errors='coerce')
        result.update(null_ohlc=int(prices.isna().sum().sum()),
                      nonfinite_ohlc=int((~np.isfinite(prices)).sum().sum()),
                      nonpositive_ohlc=int((prices <= 0).sum().sum()),
                      inconsistent_ohlc_rows=int(((prices.high < prices[['open','close','low']].max(axis=1)) |
                          (prices.low > prices[['open','close','high']].min(axis=1))).sum()),
                      large_close_moves_over_25pct=int((prices.close.pct_change(fill_method=None).abs() > .25).sum()))
    return result


def schema_issues(exc):
    """Whitelist field names/codes; omit Pydantic input, context, URLs and messages."""
    fields = {'symbol','period','totalExpectedBars','previousClosePrice','totalGainLoss',
              'totalGainLossPercentage','preMarket','regularMarket','afterMarket','bars',
              'expectedBars','timestamp','open','high','low','close','volume','value',
              'gainAmount','gainPercentage','lastRegularTradingSessionClose','closeDate','change','percentChange'}
    codes = {'missing','decimal_type','decimal_parsing','finite_number','int_type','int_parsing',
             'string_type','list_type','model_type','dict_type','float_type','float_parsing'}
    groups = {}
    for error in exc.errors(include_input=False, include_url=False, include_context=False):
        loc = '.'.join(str(x) if isinstance(x,int) else x if x in fields else '?' for x in error['loc'])
        code = error['type'] if error['type'] in codes else 'schema_validation'
        key = (loc, code)
        groups[key] = groups.get(key,0) + 1
    return [dict(field=field,code=code,count=count) for (field,code),count in list(groups.items())[:20]]
