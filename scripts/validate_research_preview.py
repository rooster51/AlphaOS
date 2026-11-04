"""Read-only SPY/QQQ audit. Only observed contracts/prices become live inputs.

This is a validation tool, not a strategy generator used by the product. It
chooses the first admissible nearby observed legs, never ranks opportunities.
Output is evidence at capture time, never an executable quote or recommendation.
"""
import argparse
from datetime import datetime, timezone
from itertools import combinations
import json
from math import inf, isclose, isfinite
import os
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

import requests

FAMILIES = ("long_call", "long_put", "call_debit_spread", "put_debit_spread",
    "put_credit_spread", "call_credit_spread", "call_butterfly", "put_butterfly",
    "bullish_bwb", "bearish_bwb", "iron_condor")


def expiration_payoff(legs, credit, fees=0):
    """Independent piecewise-linear check; does not call AlphaOS economics."""
    knots = sorted({0., *(float(leg['strike']) for leg in legs)})
    def value(spot):
        return credit*100-fees+100*sum(leg['qty']*max(0,
            spot-leg['strike'] if leg['type']=='Call' else leg['strike']-spot) for leg in legs)
    values = [value(spot) for spot in knots]
    slope = 100*sum(leg['qty'] for leg in legs if leg['type']=='Call')
    roots = [spot for spot, amount in zip(knots, values) if abs(amount)<1e-8]
    for left,right,a,b in zip(knots,knots[1:],values,values[1:]):
        if a*b<0: roots.append(left-a*(right-left)/(b-a))
    if slope and values[-1]*slope<0: roots.append(knots[-1]-values[-1]/slope)
    return dict(max_profit=inf if slope>0 else max(values),
        max_loss=inf if slope<0 else max(0,-min(values)), breakevens=sorted(set(roots)))


def equal(actual, expected):
    if expected == inf: return actual == 'unlimited'
    return isinstance(actual,(int,float)) and isclose(actual,expected,rel_tol=1e-8,abs_tol=1e-6)


def check_economics(research, request):
    expected=expiration_payoff(request['legs'],request['credit'],request['fees'])
    payoff=research.get('payoff',{})
    failures=[name for name in ('max_profit','max_loss') if not equal(payoff.get(name),expected[name])]
    roots=payoff.get('breakevens',[])
    if len(roots)!=len(expected['breakevens']) or any(not equal(a,b) for a,b in zip(roots,expected['breakevens'])):
        failures.append('breakevens')
    for key,expected_value in [('option_premium',request['credit']*100),('net_cash',request['credit']*100-request['fees'])]:
        if not equal(payoff.get(key),expected_value): failures.append(key)
    if not equal(research.get('capital_at_risk'),expected['max_loss']): failures.append('capital_at_risk')
    for key,value in [('entry_debit',max(0,-request['credit'])),('entry_credit',max(0,request['credit']))]:
        if key in research and not equal(research[key],value): failures.append(key)
    if len(request['legs'])==1:
        if not equal(research.get('premium_per_share'),-request['credit']/request['legs'][0]['qty']): failures.append('premium_per_share')
    if len(request['legs'])==2:
        width=abs(request['legs'][0]['strike']-request['legs'][1]['strike'])
        if not equal(payoff.get('width'),width): failures.append('width')
    ratio=expected['max_profit']/expected['max_loss'] if isfinite(expected['max_profit']) and expected['max_loss']>0 else None
    if ratio is not None and not equal(payoff.get('return_on_risk'),ratio): failures.append('return_on_risk')
    if research.get('trade',{}).get('expiration')!=request['expiration']: failures.append('expiration')
    if research.get('trade',{}).get('legs')!=request['legs']: failures.append('legs')
    return failures


def observed_cases(symbol, expiration, quote, chain, as_of):
    evaluated=datetime.fromisoformat(chain['quality']['evaluated_at'])
    pools={'Call':[], 'Put':[]}
    excluded=0
    for kind,side in [('Call','calls'),('Put','puts')]:
        for row in chain['chain'][side]:
            try:
                assert row['type']==kind and 0<=row['bid']<=row['ask'] and row['ask']>0
                assert all(isfinite(row[k]) for k in ('strike','bid','ask'))
                identity=re.fullmatch(r'([A-Z]+)(\d{6})([CP])(\d{8})',row['contract'])
                assert identity and identity[1]==symbol and identity[2]==expiration[2:].replace('-','')
                assert identity[3]==kind[0] and int(identity[4])/1000==row['strike']
                assert all(0<=(evaluated-datetime.fromisoformat(row[k])).total_seconds()<=900
                    for k in ('bid_timestamp','ask_timestamp'))
                pools[kind].append(row)
            except (AssertionError,KeyError,TypeError,ValueError): excluded+=1
    spot=quote['quote']['last']
    for kind in pools: pools[kind].sort(key=lambda row:abs(row['strike']-spot))
    chosen={}
    def add(family, observed):
        if family in chosen: return
        legs=[dict(type=r['type'],strike=r['strike'],qty=qty) for r,qty in observed]
        credit=-sum(qty*(r['ask'] if qty>0 else r['bid']) for r,qty in observed)
        stats=expiration_payoff(legs,credit)
        if stats['max_profit']<=0 or stats['max_loss']<=0: return
        if 'debit_spread' in family and credit>=0: return
        if ('credit_spread' in family or family=='iron_condor') and credit<=0: return
        chosen[family]=dict(request=dict(symbol=symbol,expiration=expiration,as_of=as_of,
            spot=spot,credit=credit,fees=0.,legs=legs),
            quote_evidence=[{**r,'qty':qty} for r,qty in observed],
            quoted_at=chain['retrieved_at'], pricing='Observed buy ask / sell bid; zero-fee scenario, not a fill')
    for kind in pools:
        rows=pools[kind][:30]
        for row in rows: add('long_call' if kind=='Call' else 'long_put',[(row,1)])
        for left,right in combinations(rows,2):
            low,high=sorted((left,right),key=lambda r:r['strike'])
            if kind=='Call':
                add('call_debit_spread',[(low,1),(high,-1)])
                add('call_credit_spread',[(low,-1),(high,1)])
            else:
                add('put_debit_spread',[(low,-1),(high,1)])
                add('put_credit_spread',[(low,1),(high,-1)])
        for triple in combinations(rows,3):
            low,body,high=sorted(triple,key=lambda r:r['strike'])
            a,b=body['strike']-low['strike'],high['strike']-body['strike']
            observed=[(low,1),(body,-2),(high,1)]
            if isclose(a,b): add('call_butterfly' if kind=='Call' else 'put_butterfly',observed)
            elif kind=='Put' and a>b: add('bullish_bwb',observed)
            elif kind=='Call' and b>a: add('bearish_bwb',observed)
    puts=sorted(pools['Put'][:30],key=lambda r:r['strike'])
    calls=sorted(pools['Call'][:30],key=lambda r:r['strike'])
    for pl,ps in combinations(puts,2):
        for cs,cl in combinations(calls,2):
            if ps['strike']<spot<cs['strike']: add('iron_condor',[(pl,1),(ps,-1),(cs,-1),(cl,1)])
            if 'iron_condor' in chosen: break
        if 'iron_condor' in chosen: break
    return chosen,excluded


def run(args):
    from modules.expiration_coverage import classify_expiration
    for url in (args.backend,args.preview):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise SystemExit('Use HTTPS origins without embedded credentials, query strings or fragments.')
    token=os.environ.get('ALPHAOS_API_TOKEN')
    if args.env_file:
        from dotenv import dotenv_values
        token=dotenv_values(args.env_file).get('ALPHAOS_API_TOKEN')
    if not token: raise SystemExit('Existing API credential required; never pass its value on the command line.')
    report=dict(captured_at=datetime.now(timezone.utc).isoformat(),symbols={},errors=[])
    today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    def call(target,path,body=None):
        base=args.backend if target=='api' else args.preview
        headers={'Authorization':'Bearer '+token} if target=='api' else {}
        start=time.monotonic()
        try:
            response=requests.request('GET' if body is None else 'POST',base+path,
                headers=headers,json=body,timeout=35 if '/chain/' in path else 25)
            result=dict(status=response.status_code,elapsed_ms=round((time.monotonic()-start)*1000),
                request_id=response.headers.get('X-AlphaOS-Request-ID'),body=response.json())
        except (requests.RequestException,ValueError):
            result=dict(status=None,elapsed_ms=round((time.monotonic()-start)*1000),error='transport_or_json_error')
        return result
    report['health']=call('preview','/api/health')
    for symbol in ('SPY','QQQ'):
        data=report['symbols'][symbol]=dict(horizons={})
        data['expirations']=call('api',f'/v1/options/{symbol}/expirations')
        data['quote']=call('api',f'/v1/quote/{symbol}')
        data['observation']=call('preview','/api/research/market',dict(symbol=symbol,view='observation'))
        dates=data['expirations'].get('body',{}).get('evidence',{}).get('expirations',[])
        classified={e:classify_expiration(today,e) for e in dates if e>=today}
        choices={
            '0dte':next((e for e in dates if e==today),None),
            'weekly':next((e for e,c in classified.items() if c['horizon']=='weekly' and datetime.fromisoformat(e).weekday()==4),None),
            'monthly':next((e for e,c in classified.items() if c['horizon']=='monthly'),None),
            'long_dated':next((e for e,c in classified.items() if c['calendar_dte']>=365),None),
        }
        for horizon,expiry in choices.items():
            item=data['horizons'][horizon]=dict(expiration=expiry,cases={})
            if expiry is None:
                item['blocked']='provider_did_not_list_expiration'; continue
            for target in ('api','preview'):
                item['market_'+target]=call(target,'/v1/research/market' if target=='api' else '/api/research/market',
                    dict(symbol=symbol,expiration=expiry,available_capital=500))
            chain=call('api',f'/v1/options/{symbol}/chain/{expiry}')
            item['chain']=chain
            if chain.get('status')!=200 or data['quote'].get('status')!=200:
                item['blocked']='chain_or_underlying_unavailable'; continue
            cases,excluded=observed_cases(symbol,expiry,data['quote']['body']['evidence'],chain['body']['evidence'],today)
            cases={family:cases[family] for family in FAMILIES if family in cases}
            item['excluded_contracts']=excluded
            for family in FAMILIES:
                item['cases'][family]=cases.get(family,dict(blocked='no_admissible_observed_legs_or_cashflow'))
            requests_=[c['request'] for c in cases.values()]
            if not requests_: continue
            for target in ('api','preview'):
                prefix='/v1/research' if target=='api' else '/api/research'
                # Exercise the individual route and every family through ordered comparison.
                item['single_'+target]=call(target,prefix+'/structure',requests_[0])
                result=call(target,prefix+'/structures/compare',dict(structures=requests_))
                item['comparison_'+target]=result
                body=result.get('body',{})
                if target=='preview': body=body.get('research',{})
                researched=body.get('research',{}).get('candidates',[])
                comparison=body.get('research',{}).get('comparison',{})
                result['no_recommendation']=comparison.get('winner') is None and comparison.get('recommendation') is None
                for index,(family,case) in enumerate(cases.items()):
                    case[target+'_status']=result.get('status')
                    case[target+'_checks']=check_economics(researched[index],case['request']) if index<len(researched) else ['no_researched_candidate']
                print(json.dumps(dict(symbol=symbol,horizon=horizon,target=target,market_status=item['market_'+target].get('status'),
                    comparison_status=result.get('status'),cases=len(cases),failures={f:c[target+'_checks'] for f,c in cases.items() if c[target+'_checks']})),flush=True)
            Path(args.output).parent.mkdir(parents=True,exist_ok=True)
            Path(args.output).write_text(json.dumps(report,allow_nan=False))
    # Always preserve incomplete/data-blocked runs too. Never substitute fixtures.
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',help='Existing credential file; read only ALPHAOS_API_TOKEN')
    parser.add_argument('--backend',default='https://alphaos.onrender.com')
    parser.add_argument('--preview',default='https://codex-cloudflare-workers-alphaos-web.rfroux95.workers.dev')
    parser.add_argument('--output',default='diagnostics/spy-qqq-validation.json')
    args=parser.parse_args()
    run(args)
