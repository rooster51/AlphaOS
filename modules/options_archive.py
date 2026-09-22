"""Archive observable quotes without scanner filters, pricing, or recommendations."""
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import math
import re
from zoneinfo import ZoneInfo

VERSION='options-archive-v1'
NY=ZoneInfo('America/New_York')
NUMERIC=('strike','bid','ask','last','provider_mid','volume','open_interest','iv','delta','gamma','theta','vega','rho')
TIMESTAMPS=('bid_timestamp','ask_timestamp','last_timestamp')
PROVENANCE={
    'contract':'Public instrument.symbol','quote_outcome':'Public outcome',
    'symbol':'requested underlying, checked against response baseSymbol and OSI root',
    'expiration':'requested chain expiration, checked against OSI identifier',
    'type':'Public calls/puts collection, checked against OSI identifier',
    'strike':'Public optionDetails.strikePrice','bid':'Public bid','ask':'Public ask','last':'Public last',
    'provider_mid':'Public optionDetails.midPrice','mid':'derived (bid+ask)/2 only for finite nonnegative uncrossed quotes',
    'volume':'Public volume (date of last trade)','open_interest':'Public openInterest (as-of unspecified)',
    **{f:'Public optionDetails.greeks.'+('impliedVolatility' if f=='iv' else f) for f in ('iv','delta','gamma','theta','vega','rho')},
    **{f:'Public '+f.replace('_timestamp','Timestamp') for f in TIMESTAMPS},
    'dte':'derived expiration minus New York collection date, calendar days',
    'observed_at':'collector UTC timestamp after chain response; not a quote timestamp'}
LIMITATIONS=[
    'Last available provider quotes; delay and market-close/EOD status are not guaranteed.',
    'Sequential expiration requests are not simultaneous. Keep per-request and provider timestamps.',
    'IV/Greeks are optional provider model values, not historical frequencies or option POP; IV scale is not certified by the SDK contract.',
    'Expired 0-DTE chains may be absent after collection time. No missing contracts or fields are manufactured.',
    'Volume is for the last-trade date; open-interest as-of is unspecified. No liquidity/attractiveness filter is applied.'
]


def timestamp(value):
    if isinstance(value,datetime):
        parsed=value
    elif isinstance(value,str):
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    else:
        raise ValueError('Timestamp missing or invalid.')
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include a timezone.')
    return parsed.astimezone(timezone.utc)


def number(value):
    if value is None:
        return None,False
    try:
        if isinstance(value,bool): raise ValueError
        n=float(value)
        if not math.isfinite(n): raise ValueError
        return n,False
    except (ValueError,TypeError,OverflowError):
        return None,True


def normalize_contract(raw,symbol,expiration,kind,observed_at,snapshot_date):
    """Retain malformed observations with explicit field errors, not raw payloads."""
    errors=[]; warnings=[]
    if not isinstance(raw,dict):
        raw={};errors.append('record_not_object')
    instrument=raw.get('instrument') if isinstance(raw.get('instrument'),dict) else {}
    details=raw.get('optionDetails') if isinstance(raw.get('optionDetails'),dict) else {}
    greeks=details.get('greeks') if isinstance(details.get('greeks'),dict) else {}
    contract=instrument.get('symbol')
    match=re.fullmatch(r'([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})',contract) if isinstance(contract,str) else None
    row=dict(symbol=symbol,contract=contract if match else None,expiration=expiration,type=kind,
             observed_at=observed_at,dte=None,mid=None,
             quote_outcome=raw.get('outcome') if raw.get('outcome') in ('SUCCESS','UNKNOWN') else None)
    if not match:
        errors.append('invalid_contract_identifier')
        row['invalid_contract_identifier_sha256']=hashlib.sha256(str(contract).encode()).hexdigest()
    if instrument.get('type')!='OPTION': errors.append('instrument_not_option')
    if row['quote_outcome']!='SUCCESS': warnings.append('quote_outcome_not_success')
    if kind not in ('call','put'): errors.append('invalid_option_type')
    try:
        expiry=date.fromisoformat(expiration)
        row['dte']=(expiry-date.fromisoformat(snapshot_date)).days
        if row['dte']<0: errors.append('expired_before_snapshot')
    except (TypeError,ValueError):
        errors.append('invalid_expiration');row['expiration']=None
    source=dict(strike=details.get('strikePrice'),provider_mid=details.get('midPrice'),
        **{f:raw.get(f) for f in ('bid','ask','last','volume')},open_interest=raw.get('openInterest'),
        iv=greeks.get('impliedVolatility'),**{f:greeks.get(f) for f in ('delta','gamma','theta','vega','rho')})
    for field,value in source.items():
        row[field],bad=number(value)
        if bad: errors.append(field+'_nonfinite_or_nonnumeric')
    if row['strike'] is None or row['strike']<=0: errors.append('invalid_strike')
    for field in ('bid','ask','last','provider_mid','volume','open_interest','iv'):
        if row[field] is not None and row[field]<0: errors.append(field+'_negative')
    for field in ('volume','open_interest'):
        if row[field] is not None and not row[field].is_integer(): errors.append(field+'_not_integer')
    if match:
        root,day,side,strike=match.groups()
        if root!=symbol: errors.append('contract_underlying_mismatch')
        try:
            osi_date=datetime.strptime(day,'%y%m%d').date().isoformat()
            if osi_date!=expiration: errors.append('contract_expiration_mismatch')
        except ValueError: errors.append('invalid_contract_expiration')
        if ('call' if side=='C' else 'put')!=kind: errors.append('contract_type_mismatch')
        if row['strike'] is not None and abs(int(strike)/1000-row['strike'])>1e-9: errors.append('contract_strike_mismatch')
    try:
        collected=timestamp(observed_at)
        if collected.astimezone(NY).date().isoformat()!=snapshot_date: errors.append('collection_date_mismatch')
    except ValueError:
        collected=None;errors.append('invalid_observed_at');row['observed_at']=None
    for field in TIMESTAMPS:
        value=raw.get(field.replace('_timestamp','Timestamp'))
        row[field]=None
        if value is not None:
            try:
                parsed=timestamp(value);row[field]=parsed.isoformat()
                if collected and parsed>collected: errors.append(field+'_in_future')
                if parsed.astimezone(NY).date().isoformat()!=snapshot_date: warnings.append(field+'_different_session')
            except ValueError: errors.append(field+'_invalid')
        elif field!='last_timestamp': warnings.append(field+'_missing')
    bid,ask=row['bid'],row['ask']
    if bid is None or ask is None: warnings.append('incomplete_bid_ask')
    elif bid>=0 and ask>=0:
        if ask<bid: errors.append('crossed_bid_ask')
        else: row['mid']=(bid+ask)/2
    row.update(rejection_reasons=sorted(set(errors)),quality_warnings=sorted(set(warnings)),
               missing_fields=[f for f in (*NUMERIC,*TIMESTAMPS) if row.get(f) is None])
    return row


def build_options_snapshot(provider,symbol,session,config,config_version,config_hash,code_revision=None):
    start=timestamp(provider.now())
    snapshot_date=start.astimezone(NY).date().isoformat()
    if symbol not in ('SPY','QQQ') or snapshot_date!=session:
        raise ValueError('Options collection must occur on the actual session date.')
    underlying=provider.underlying(symbol)
    instrument=underlying.get('instrument',{})
    spot,bad=number(underlying.get('last'))
    if instrument.get('symbol')!=symbol or instrument.get('type')!='EQUITY' or underlying.get('outcome')!='SUCCESS' or bad or spot is None or spot<=0:
        raise ValueError('Underlying quote is missing, invalid or mismatched.')
    spot_time=None;warnings=LIMITATIONS.copy()
    if underlying.get('lastTimestamp') is not None:
        spot_time=timestamp(underlying['lastTimestamp'])
        if spot_time>timestamp(provider.now()): raise ValueError('Underlying quote timestamp is in the future.')
        if spot_time.astimezone(NY).date().isoformat()!=session: warnings.append('Underlying last trade is from a different session; strike band uses last available price.')
    else: warnings.append('Underlying last-trade timestamp unavailable.')
    expirations=provider.expirations(symbol)
    selected=[];excluded_expirations=0;invalid_expirations=0
    for expiration in expirations:
        try:
            if not isinstance(expiration,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',expiration): raise ValueError
            dte=(date.fromisoformat(expiration)-date.fromisoformat(session)).days
        except (ValueError,TypeError): invalid_expirations+=1;continue
        if config['min_dte']<=dte<=config['max_dte']: selected.append(expiration)
        else: excluded_expirations+=1
    records=[];requests=[];failures=[]
    for expiration in sorted(set(selected)):
        request_start=timestamp(provider.now()).isoformat()
        try:
            chain=provider.chain(symbol,expiration)
            observed=timestamp(provider.now()).isoformat()
            if not all(isinstance(chain.get(k),list) for k in ('calls','puts')): raise ValueError
            requests.append(dict(expiration=expiration,started_at=request_start,received_at=observed))
            for kind,bucket in (('call','calls'),('put','puts')):
                records += [normalize_contract(raw,symbol,expiration,kind,observed,session) for raw in chain[bucket]]
        except Exception:
            failures.append(dict(expiration=expiration,reason='chain_retrieval_failed'))
    counts=Counter(r['contract'] for r in records if r['contract'])
    valid=[];questionable=[];rejected=[];excluded_strikes=0
    for row in records:
        if row['contract'] and counts[row['contract']]>1: row['rejection_reasons'].append('duplicate_contract_identifier')
        if row['rejection_reasons']: rejected.append(row);continue
        if abs(row['strike']/spot-1)>config['strike_band']+1e-12:
            excluded_strikes+=1;continue
        (questionable if row['quality_warnings'] else valid).append(row)
    for group in (valid,questionable,rejected):
        group.sort(key=lambda r:(r.get('expiration') or '',r.get('contract') or '',r.get('type') or ''))
    end=timestamp(provider.now())
    if end.astimezone(NY).date().isoformat()!=session: raise ValueError('Collection crossed the session-date boundary.')
    if failures: warnings.append('One or more expiration requests failed; archive is partial.')
    if invalid_expirations: warnings.append('Malformed expiration entries were rejected; archive is partial.')
    if not records: warnings.append('No contract observations returned for the configured universe.')
    if not selected: warnings.append('No available expirations in the configured DTE window; absent 0-DTE data is not fabricated.')
    kept=valid+questionable+rejected
    return dict(schema_version=VERSION,config_version=config_version,config_sha256=config_hash,code_revision=code_revision,
        symbol=symbol,snapshot_date=session,collection_started_at=start.isoformat(),generated_at=end.isoformat(),
        provider=provider.name,quote_timing='last_available_not_guaranteed_close',underlying_price=spot,
        underlying_last_timestamp=spot_time.isoformat() if spot_time else None,universe=config,
        status='partial' if failures or invalid_expirations else 'complete' if records else 'empty',
        provenance=PROVENANCE,warnings=warnings,requested_expirations=sorted(set(selected)),requests=requests,
        expiration_failures=failures,invalid_expiration_count=invalid_expirations,
        excluded_expiration_count=excluded_expirations,excluded_strike_count=excluded_strikes,received_contract_count=len(records),
        valid_contracts=valid,questionable_contracts=questionable,rejected_contracts=rejected,
        rejection_counts=dict(Counter(reason for row in rejected for reason in row['rejection_reasons'])),
        missing_field_counts={f:sum(row.get(f) is None for row in kept) for f in (*NUMERIC,*TIMESTAMPS)})
