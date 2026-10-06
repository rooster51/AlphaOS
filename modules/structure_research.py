"""Small adapters for existing debit, butterfly/BWB and condor candidates.

No construction factory or pricing model: expiration economics come exclusively
from options_payoff. Market observations are optional, never synthesized.
"""
from copy import deepcopy
from datetime import date
from math import isclose, isfinite

from modules.options_payoff import trade_analysis, validate_trade


def _number(value):
    if isinstance(value,bool):return None
    try:
        value=float(value)
        return value if isfinite(value) else None
    except (TypeError,ValueError):return None


def _family(legs):
    legs=sorted(legs,key=lambda l:(l['type'],l['strike']))
    if len({(l['type'],l['strike']) for l in legs})!=len(legs):
        raise ValueError('Duplicate option legs are ambiguous.')
    kinds={l['type'] for l in legs}
    if len(legs)==2 and len(kinds)==1:
        low,high=legs
        if low['qty']==-high['qty']:
            if low['type']=='Call' and low['qty']>0:return 'call_debit_spread','bullish'
            if low['type']=='Put' and high['qty']>0:return 'put_debit_spread','bearish'
            if low['type']=='Put' and low['qty']>0:return 'put_credit_spread','bullish'
            if low['type']=='Call' and high['qty']>0:return 'call_credit_spread','bearish'
    if len(legs)==3 and len(kinds)==1:
        low,body,high=legs
        if low['qty']>0 and high['qty']==low['qty'] and body['qty']==-2*low['qty']:
            lower,upper=body['strike']-low['strike'],high['strike']-body['strike']
            if isclose(lower,upper,rel_tol=1e-9):return 'butterfly','neutral'
            if low['type']=='Put' and lower>upper:return 'bullish_bwb','bullish'
            if low['type']=='Call' and upper>lower:return 'bearish_bwb','bearish'
    if len(legs)==4 and kinds=={'Put','Call'}:
        puts=sorted([l for l in legs if l['type']=='Put'],key=lambda l:l['strike'])
        calls=sorted([l for l in legs if l['type']=='Call'],key=lambda l:l['strike'])
        if len(puts)==len(calls)==2:
            pl,ps=puts;cs,cl=calls;q=pl['qty']
            if q>0 and ps['qty']==cs['qty']==-q and cl['qty']==q:
                if ps['strike']<cs['strike']:return 'iron_condor','neutral'
                if ps['strike']==cs['strike'] and isclose(ps['strike']-pl['strike'],cl['strike']-cs['strike']):
                    return 'butterfly','neutral'
    raise ValueError('Unsupported or malformed structure; explicit supported legs required.')


def research_structure(candidate,*,symbol=None,spot=None,as_of=None,expected_move=None):
    """Normalize shared-engine trades or existing Strategy Selector suggestions.

    Native credit uses the shared engine's signed per-share package cashflow.
    Selector entry_price is a one-unit price; its action/quantity legs must be 1.
    Cached max-profit/loss, probability, fit, and recommendation fields are ignored.
    """
    if not isinstance(candidate,dict):raise ValueError('Candidate must be a mapping.')
    trade=deepcopy(candidate)
    if symbol is not None and trade.get('symbol') and symbol.strip().upper()!=str(trade['symbol']).strip().upper():
        raise ValueError('Underlying mismatch.')
    if spot is not None and trade.get('spot') is not None and _number(spot)!=_number(trade['spot']):
        raise ValueError('Spot mismatch.')
    trade['symbol']=str(symbol or trade.get('symbol') or '').strip().upper()
    if not trade['symbol']:raise ValueError('Underlying is required.')
    try:
        expiry=date.fromisoformat(str(trade['expiration']))
        legs=trade['legs']
        if not isinstance(legs,list) or not legs:raise ValueError('Legs required.')
        selector=all(isinstance(l,dict) and 'action' in l and 'qty' not in l for l in legs)
        if selector:
            price=_number(trade.get('entry_price'))
            if price is None or price<=0 or trade.get('side') not in ('Long / Debit','Short / Credit'):
                raise ValueError('Explicit entry price and cashflow side required.')
            for leg in legs:
                if leg.get('action') not in ('Buy','Sell') or leg.get('quantity')!=1:
                    raise ValueError('Selector adapter requires explicit one-unit legs.')
                leg['qty']=1 if leg['action']=='Buy' else -1
            signed=price*(-1 if trade['side']=='Long / Debit' else 1)
            if 'credit' in trade and trade['credit']!=signed:raise ValueError('Conflicting entry cashflows.')
            trade['credit']=signed
        trade.update(spot=spot if spot is not None else trade.get('spot'),
            shares=trade.get('shares',0),fees=trade.get('fees',0),source=trade.get('source') or 'Supplied candidate')
        # Drop presentation scores, recommendations and stale cached economics.
        trade={k:trade[k] for k in ('symbol','strategy','expiration','spot','credit','shares','fees','source','legs','pricing_assumption') if k in trade}
        trade=validate_trade(trade)
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('Incomplete candidate.') from exc
    if trade['shares']!=0:raise ValueError('Only option-only structures are supported.')
    family,direction=_family(trade['legs'])
    if family.endswith('debit_spread') and trade['credit']>=0:raise ValueError('Debit spread requires a debit.')
    if family in ('iron_condor','put_credit_spread','call_credit_spread') and trade['credit']<=0:raise ValueError('Iron condor requires a credit.')
    trade['strategy_family']=family
    trade['strategy']=family
    analysis=trade_analysis(trade)
    if not all(isfinite(analysis[k]) and analysis[k]>0 for k in ('max_profit','max_loss')):
        raise ValueError('Candidate must have finite positive potential profit and risk.')
    dte=None if as_of is None else (expiry-date.fromisoformat(str(as_of))).days
    if dte is not None and dte<0:raise ValueError('Expiration precedes research date.')
    em=_number(expected_move)
    if expected_move is not None and (em is None or em<0):raise ValueError('Expected move must be a nonnegative dollar amount.')
    roots=analysis['breakevens'];moves=[b-trade['spot'] for b in roots]
    quote_fields=('contract','bid','ask','mid','bid_timestamp','ask_timestamp','delta','gamma','theta','vega','rho','iv','volume','open_interest')
    evidence=[{key:leg.get(key) for key in quote_fields} for leg in trade['legs']]
    return dict(version='structure-research-v1',underlying=trade['symbol'],strategy_family=family,direction=direction,
        expiration=trade['expiration'],legs=trade['legs'],trade=trade,
        entry_debit=max(0,-trade['credit']),entry_credit=max(0,trade['credit']),
        capital_at_risk=analysis['max_loss'],max_loss=analysis['max_loss'],max_profit=analysis['max_profit'],
        breakeven=roots[0] if len(roots)==1 else None,breakevens=roots,
        required_move=moves[0] if len(moves)==1 else None,
        required_move_pct=moves[0]/trade['spot'] if len(moves)==1 else None,
        breakeven_moves=[dict(breakeven=b,move=m,move_pct=m/trade['spot']) for b,m in zip(roots,moves)],
        dte=dte,expected_move_context=None if em is None else dict(expected_move=em,expected_move_pct=em/trade['spot'],
            breakeven_distances_in_expected_moves=[abs(m)/em if em else None for m in moves],source='Caller-supplied context; horizon not inferred'),
        payoff=analysis,evidence=dict(source=trade['source'],option_legs=evidence,
            expected_move_status='unknown' if em is None else 'supplied',pricing_assumption=trade.get('pricing_assumption','Supplied entry cashflow; not a verified fill')),
        candidate_order='input/generator order; not a ranking',
        caveats=['Deterministic expiration payoff, not a forecast or probability of profit.',
            'Standard 100-share multiplier; credit/debit are per-share package cashflows; payoff/risk and fees are dollars.',
            'Signed moves are distances to expiration breakevens, not predicted moves. Multiple roots remain separate.',
            'Direction describes structure bias, not inferred market evidence. No winner or recommendation.',
            'Missing Greeks, IV, liquidity, timestamps and expected-move evidence remain unavailable.'])


def discover_debit_spreads(chain,spot,*,directions=('bullish','bearish'),width=1,as_of=None,expected_move=None):
    """Reuse the existing debit constructor without its missing-delta fallback.

    Midpoint-priced research, not natural fills. Invalid/ambiguous contracts are
    excluded before selection; no new provider requests or ranking are performed.
    """
    from modules.options_suggestions import _debit_spread
    from modules.premium_engine import valid_contract
    spot=_number(spot);width=_number(width)
    if spot is None or spot<=0 or width is None or width<=0:raise ValueError('Positive spot and width required.')
    if not isinstance(chain,dict) or not chain.get('symbol'):raise ValueError('Normalized chain symbol required.')
    date.fromisoformat(str(chain.get('expiration')))
    if not directions or not set(directions)<={'bullish','bearish'}:raise ValueError('Explicit bullish/bearish directions required.')
    clean=dict(symbol=chain['symbol'],expiration=chain['expiration']);excluded=0
    for key,kind in (('calls','Call'),('puts','Put')):
        rows=chain.get(key) or []
        if not isinstance(rows,list):raise ValueError('Chain pools must be lists.')
        strikes=[_number(l.get('strike')) for l in rows if isinstance(l,dict)]
        clean[key]=[]
        for leg in rows:
            if not isinstance(leg,dict) or leg.get('type')!=kind or not valid_contract(leg):excluded+=1;continue
            delta=_number(leg.get('delta'))
            if delta is None or not (-1<=delta<0 if kind=='Put' else 0<delta<=1) or strikes.count(_number(leg['strike']))!=1:
                excluded+=1;continue
            if leg.get('expiration',chain['expiration'])!=chain['expiration']:excluded+=1;continue
            clean[key].append({**leg,'strike':float(leg['strike']),'bid':float(leg['bid']),'ask':float(leg['ask']),
                'delta':delta,'mid':(float(leg['bid'])+float(leg['ask']))/2})
    results=[]
    for direction in dict.fromkeys(directions):
        candidate=_debit_spread(clean,spot,direction.title(),'Research',width)
        if candidate is None:continue
        # Restore observations dropped by the legacy presentation-leg formatter.
        for leg in candidate['legs']:
            source=next(l for l in clean['calls' if leg['type']=='Call' else 'puts'] if l['strike']==leg['strike'])
            leg.update({k:v for k,v in source.items() if k not in ('qty','action','quantity')})
        candidate.update(source='Public normalized chain',pricing_assumption='Existing constructor midpoint debit (rounded to cents); not an executable fill')
        results.append(research_structure(candidate,symbol=chain['symbol'],spot=spot,as_of=as_of,expected_move=expected_move))
    return dict(version='debit-discovery-v1',candidates=results,excluded_contract_count=excluded,
        candidate_order='requested direction order; not a ranking',
        caveats=['Observed delta and valid bid/ask required by the reused selector; missing evidence produces no candidate.',
            'Requested wing width is a target; the existing constructor may use the nearest available width. Actual legs/payoff are authoritative.'])
