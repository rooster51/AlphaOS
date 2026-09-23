"""Integrated research orchestration. No orders, ranking, or archive writes."""
from datetime import date
import numpy as np
import pandas as pd
from modules.market_state import validate_ohlc, market_state_features
from modules.market_outcomes import forward_outcomes, HORIZONS
from modules.historical_analogs import analog_research, DEFAULT_TOLERANCES
from modules.price_structure import price_structure, nearest_levels
from modules.forward_distribution import summarize_forward_distribution
from modules.level_behavior import level_behavior
from modules.threshold_survival import threshold_research
from modules.option_scenario_ev import scenario_economics
from modules.options_payoff import validate_trade, trade_analysis
from modules.daily_archive import digest

VERSION = 'phase6-workspace-v1'


def vertical_context(trade, structure):
    t=validate_trade(trade); legs=t['legs']
    if t['shares'] or len(legs)!=2 or legs[0]['type']!=legs[1]['type']:
        raise ValueError('Select a plain two-leg vertical credit spread without stock.')
    short=[l for l in legs if l['qty']<0]; long=[l for l in legs if l['qty']>0]
    if len(short)!=1 or len(long)!=1 or short[0]['qty']!=-long[0]['qty']:
        raise ValueError('The vertical needs equal long and short quantities.')
    short,long=short[0],long[0]; put=short['type']=='Put'
    width=(short['strike']-long['strike']) if put else (long['strike']-short['strike'])
    if width<=0 or not 0<t['credit']<width*abs(short['qty']):
        raise ValueError('Credit must be positive and below total vertical width; check leg direction.')
    expiry=date.fromisoformat(t['expiration'])
    analysis=trade_analysis(t)
    side='support' if put else 'resistance'
    levels=structure['levels']; near=levels[levels.side==side] if not levels.empty else levels
    nearest=None if near.empty else float(near.iloc[0].level)
    return dict(strategy='Put credit spread' if put else 'Call credit spread',symbol=t['symbol'],
        expiration=expiry.isoformat(),current_spot=t['spot'],research_close=structure['research_close'],
        short_strike=short['strike'],long_strike=long['strike'],breakeven=analysis['breakevens'][0],
        credit=t['credit'],max_profit=analysis['max_profit'],max_loss=analysis['max_loss'],
        return_on_risk=analysis['return_on_risk'],strike_distance_pct=short['strike']/t['spot']-1,
        strike_distance_atr=(short['strike']-t['spot'])/structure['atr'],nearest_structural_level=nearest,
        strike_minus_nearest_level=None if nearest is None else short['strike']-nearest,mode='put' if put else 'call')


def selected_evidence(analog, trade, structure, horizon, **friction):
    context=vertical_context(trade,structure)
    bridged={**analog,'target':dict(analog['target'])}
    bridged['target']['close']=trade['spot']
    threshold=threshold_research(bridged,context['mode'],horizon,
        threshold_price=context['short_strike'],allow_opposite=True)
    economics=scenario_economics(analog,trade,horizon,**friction)
    return dict(context=context,threshold=threshold,economics=economics)


def research_workspace(history, trade, completed_before, horizon=3, method='tolerance', metadata=None, prepared=None, **friction):
    t=validate_trade(trade)
    bars,audit=validate_ohlc(history,completed_before)
    if bars.symbol.iloc[0]!=t['symbol']: raise ValueError('Trade and research symbol must match.')
    reusable=False
    if prepared:
        try:
            source=prepared['dataset']
            reusable=(prepared['snapshot_id']==digest({k:v for k,v in prepared.items() if k!='snapshot_id'})
                and digest(source['features'][['date','symbol','open','high','low','close']])==digest(bars))
        except (KeyError,TypeError,ValueError): pass
        if not reusable: raise ValueError('Prepared research does not match the completed OHLC prefix.')
    features=prepared['dataset']['features'] if reusable else market_state_features(bars,completed_before)
    outcomes=prepared['dataset']['outcomes'] if reusable else forward_outcomes(bars,completed_before)
    structure=price_structure(bars,completed_before=completed_before,anchor_spot=t['spot'])
    samples={}
    for h in HORIZONS:
        if reusable and method=='tolerance' and prepared['horizon']==h:
            samples[h]=prepared['analog']
        else:
            samples[h]=analog_research(features,outcomes,method=method,horizon=h)
    if horizon not in samples: raise ValueError('Unsupported observed-session horizon.')
    primary=samples[horizon]
    evidence=selected_evidence(primary,t,structure,horizon,**friction)
    distributions={h:summarize_forward_distribution(a,h,t['spot']) for h,a in samples.items()}
    levels=[]; details=[]
    for row in nearest_levels(structure).to_dict('records'):
        result=level_behavior(primary,horizon=horizon,anchor_spot=t['spot'],level=row['level'],side=row['side'])
        levels.append({**row,**result['summary']}); details.append(result)
    robustness=[]
    for name,mult in [('Tight tolerance',.75),('Default tolerance',1.),('Wide tolerance',1.5),('Nearest 50',None)]:
        args=dict(method='nearest',neighbors=50) if mult is None else dict(method='tolerance',tolerances={k:v*mult for k,v in DEFAULT_TOLERANCES.items()})
        analog=primary if name=='Default tolerance' and method=='tolerance' else analog_research(features,outcomes,horizon=horizon,**args)
        ev=scenario_economics(analog,t,horizon,**friction)
        robustness.append(dict(sample=name,**ev['net_summary']))
    robustness.append(dict(sample='Primary non-overlapping diagnostic',**evidence['economics']['non_overlapping_net_summary']))
    return dict(version=VERSION,trade=t,structure=structure,levels=pd.DataFrame(levels),level_details=details,
        distributions=distributions,primary=primary,evidence=evidence,robustness=pd.DataFrame(robustness),
        provenance=dict(source=metadata or {},ohlc_sha256=digest(bars),audit=audit,
                        completed_before=str(completed_before),research_date=str(bars.date.iloc[-1].date()),
                        horizon=horizon,method=method,friction=friction))


def compare_candidates(trades, research, as_of, **friction):
    rows=[]; rejected=[]
    for index,trade in enumerate(trades):
        try:
            if trade['symbol']!=research['trade']['symbol'] or trade['spot']!=research['trade']['spot']:
                raise ValueError('Candidate symbol and current spot must match the research workspace.')
            evidence=selected_evidence(research['primary'],trade,research['structure'],research['provenance']['horizon'],**friction)
            c=evidence['context']; s=evidence['threshold']['summary']; ev=evidence['economics']['net_summary']
            dte=(date.fromisoformat(c['expiration'])-date.fromisoformat(str(as_of))).days
            if dte<0: raise ValueError('Expired candidate.')
            rows.append({**c,'DTE':dte,'terminal_survival_frequency':s['survival_frequency'],
                'touch_breach_frequency':s['touch_frequency'],'scenario_expected_payoff':ev['expected_payoff'],
                'positive_payoff_frequency':ev['positive_frequency'],'EV_max_risk':ev['expected_payoff_on_max_risk'],
                'analog_N':ev['n'],'source':trade['source'],'quote_provenance':trade.get('quote_provenance')})
        except (ValueError,KeyError,TypeError) as exc:
            rejected.append(dict(candidate=index,reason=str(exc)))
    return dict(candidates=pd.DataFrame(rows),rejected=pd.DataFrame(rejected))


def chain_verticals(chain, symbol, spot, as_of, max_candidates=200):
    """Normalized chain -> bounded one-lot candidates at short bid minus long ask.

    Quotes are illustrative executable-side proxies, never guaranteed fills.
    No filtering by research outcome and no truncation: oversize requests fail.
    """
    required={'symbol','expiration','type','strike','bid','ask','observed_at','contract'}
    if not isinstance(chain,pd.DataFrame) or not required.issubset(chain):
        raise ValueError('Chain requires '+', '.join(sorted(required))+'.')
    if len(chain)>100: raise ValueError('Select at most 100 chain contracts per comparison.')
    rows=[]; rejected=[]
    for i,row in chain.iterrows():
        try:
            if row.symbol!=symbol or row.type not in ('put','call'): raise ValueError('Wrong symbol or option type.')
            if row.get('rejection_reasons') or row.get('quality_warnings'): raise ValueError('Archived quote is rejected or questionable.')
            expiry=date.fromisoformat(str(row.expiration))
            if expiry<date.fromisoformat(str(as_of)): raise ValueError('Expired quote.')
            stamp=pd.Timestamp(row.observed_at)
            if pd.isna(stamp) or stamp.tzinfo is None: raise ValueError('Quote collection timestamp must include timezone.')
            vals=np.array([row.strike,row.bid,row.ask],dtype=float)
            if not np.isfinite(vals).all() or vals[0]<=0 or vals[1]<0 or vals[2]<vals[1]: raise ValueError('Missing, negative, or crossed quote.')
            if not isinstance(row.contract,str) or not row.contract.strip(): raise ValueError('Missing contract identifier.')
            if stamp.tz_convert('America/New_York').date()>date.fromisoformat(str(as_of)):
                raise ValueError('Quote observation is later than the comparison date.')
            normalized=row.to_dict()
            normalized.update(strike=float(vals[0]),bid=float(vals[1]),ask=float(vals[2]))
            rows.append(normalized)
        except (ValueError,TypeError) as exc: rejected.append(dict(row=i,reason=str(exc)))
    clean=pd.DataFrame(rows); trades=[]
    if not clean.empty:
        if clean.contract.duplicated().any(): raise ValueError('Duplicate contract identifiers.')
        if clean.duplicated(['expiration','type','strike']).any(): raise ValueError('Ambiguous duplicate strikes.')
        for _,group in clean.groupby(['expiration','type'],sort=True):
            for short in group.sort_values('strike').to_dict('records'):
                for long in group.sort_values('strike').to_dict('records'):
                    width=short['strike']-long['strike'] if short['type']=='put' else long['strike']-short['strike']
                    credit=short['bid']-long['ask']
                    if not 0<credit<width: continue
                    trades.append(dict(symbol=symbol,strategy='Vertical credit spread',expiration=short['expiration'],
                        spot=spot,credit=credit,fees=0,shares=0,stock_basis=spot,
                        source='Chain short bid minus long ask; hypothetical fill',
                        quote_provenance=dict(short=short,long=long),
                        legs=[dict(type=short['type'].title(),strike=short['strike'],qty=-1),
                              dict(type=long['type'].title(),strike=long['strike'],qty=1)]))
                    if len(trades)>max_candidates: raise ValueError('Too many candidates; narrow the chain explicitly. No rows were ranked or truncated.')
    return trades,pd.DataFrame(rejected)
