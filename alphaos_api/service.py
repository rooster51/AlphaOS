"""HTTP orchestration over existing AlphaOS engines; no second quant model."""
from datetime import datetime,timezone,date
from zoneinfo import ZoneInfo
from math import isfinite
import re
import pandas as pd
from modules.daily_archive import digest
from modules.selector_research import context_from_dataset,annotate_candidates
from modules.price_structure import nearest_levels
from modules.forward_distribution import summarize_forward_distribution
from modules.phase6_research import research_workspace,selected_evidence
from modules.option_scenario_ev import scenario_economics
from modules.premium_engine import generate
from modules.public_provider import provider_error
from modules.history_diagnostics import HistoryError
from .contracts import APIError,SCHEMA_VERSION,CAVEATS
from .cache import TTLStore
from .provider import MarketProvider

NY=ZoneInfo('America/New_York')
HORIZONS=(1,2,3,5,10)
QUOTE_FIELDS=('symbol','last','bid','ask','previous_close','change','change_pct','volume','updated_at')
LEG_FIELDS=('contract','type','strike','bid','ask','mid','bid_timestamp','ask_timestamp','iv','delta','gamma','theta','vega','rho','volume','open_interest')


def symbol_value(value):
    symbol=value.strip().upper()
    if symbol not in ('SPY','QQQ'):raise APIError('unsupported_symbol',400)
    return symbol


def horizon_value(value):
    if value not in HORIZONS:raise APIError('unsupported_horizon',400)
    return value


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and isfinite(value)


def stamp(value):
    if value is None:return None
    try:
        t=pd.Timestamp(value)
        if pd.isna(t) or t.tzinfo is None:return None
        return t.tz_convert('UTC').isoformat()
    except (ValueError,TypeError):return None


def required_credits(trade,economics):
    ev=economics['net_summary']['expected_payoff'];risk=economics['trade_analysis']['max_loss']
    if ev is None:return dict(required_credit_for_zero_scenario_EV=None,required_credit_for_5pct_EV_max_risk=None)
    # One-lot vertical payoff changes by exactly $100 per $1 credit.
    zero=trade['credit']-ev/100
    five=trade['credit']+(.05*risk-ev)/105
    width=abs(trade['legs'][0]['strike']-trade['legs'][1]['strike'])
    return dict(required_credit_for_zero_scenario_EV=zero,required_credit_for_5pct_EV_max_risk=five,
        zero_credit_within_vertical_width=0<zero<width,five_pct_credit_within_vertical_width=0<five<width,
        convention='Algebraic historical scenario thresholds, not fair value; same fees/friction and Phase 5.2 entry max-risk denominator.')


class ResearchService:
    def __init__(self,provider=None,clock=None):
        self.provider=provider or MarketProvider()
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.data=TTLStore(self.clock,96);self.snapshots=TTLStore(self.clock,64);self.scans=TTLStore(self.clock,32)

    def today(self):return self.clock().astimezone(NY).date()

    def provider_call(self,fn,*args):
        try:return fn(*args)
        except HistoryError as exc:
            mapped=provider_error(exc)
            if mapped.code=='provider_unavailable':raise APIError('insufficient_historical_data',503) from None
            raise APIError(mapped.code,429 if mapped.code=='public_rate_limit' else 503) from None
        except Exception as exc:
            error=provider_error(exc)
            raise APIError(error.code,429 if error.code=='public_rate_limit' else 503) from None

    def quote(self,symbol,refresh=False):
        symbol=symbol_value(symbol)
        def load():
            rows=self.provider_call(self.provider.quote,symbol)
            if not isinstance(rows,list) or any(not isinstance(q,dict) for q in rows):
                raise APIError('missing_quote',503)
            matches=[q for q in rows if q.get('symbol')==symbol]
            if len(matches)!=1 or not finite(matches[0].get('last')) or matches[0]['last']<=0:
                raise APIError('missing_quote',503)
            q={k:matches[0].get(k) for k in QUOTE_FIELDS};q['updated_at']=stamp(q['updated_at'])
            return dict(quote=q,retrieved_at=self.clock().isoformat())
        return self.data.put(('quote',symbol),load(),30) if refresh else self.data.load(('quote',symbol),30,load)

    def expiration(self,value):
        if isinstance(value,str):
            try:value=date.fromisoformat(value)
            except ValueError:raise APIError('invalid_expiration') from None
        if value<self.today():raise APIError('expired_option')
        return value.isoformat()

    def expirations(self,symbol):
        symbol=symbol_value(symbol)
        def load():
            values=self.provider_call(self.provider.expirations,symbol)
            try:values=[date.fromisoformat(x).isoformat() for x in values]
            except (ValueError,TypeError):raise APIError('provider_schema_error',503) from None
            return dict(expirations=sorted(set(values)),retrieved_at=self.clock().isoformat())
        return self.data.load(('expirations',symbol),300,load)

    def chain(self,symbol,expiration,refresh=False):
        symbol=symbol_value(symbol);expiration=self.expiration(expiration)
        if expiration not in self.expirations(symbol)['expirations']:raise APIError('expiration_unavailable',404)
        def load():
            raw=self.provider_call(self.provider.chain,symbol,expiration)
            if raw.get('symbol')!=symbol or raw.get('expiration')!=expiration or not all(isinstance(raw.get(k),list) for k in ('puts','calls')):
                raise APIError('incomplete_chain',503)
            clean=dict(symbol=symbol,expiration=expiration)
            for side in ('calls','puts'):
                if any(not isinstance(row,dict) for row in raw[side]):raise APIError('incomplete_chain',503)
                clean[side]=[{k:row.get(k) for k in LEG_FIELDS} for row in raw[side]]
                for leg in clean[side]:
                    for k in ('bid_timestamp','ask_timestamp'):leg[k]=stamp(leg[k])
            legs=clean['puts']+clean['calls']
            return dict(chain=clean,retrieved_at=self.clock().isoformat(),quality=dict(empty=not bool(legs),
                incomplete_quote_count=sum(not all(finite(l.get(k)) for k in ('bid','ask','strike')) for l in legs),
                timing=self.timing(None,legs)))
        key=('chain',symbol,expiration)
        return self.data.put(key,load(),30) if refresh else self.data.load(key,30,load)

    def snapshot(self,symbol,horizon=3,spot=None,snapshot_id=None,refresh=False,quote_bundle=None):
        symbol=symbol_value(symbol);horizon=horizon_value(horizon)
        if snapshot_id:
            bundle=self.snapshots.get(snapshot_id)
            if bundle is None:raise APIError('stale_snapshot',410)
            s=bundle['prepared']
            if s['dataset']['metadata']['symbol']!=symbol or s['horizon']!=horizon or (spot is not None and s['current_spot']!=spot):
                raise APIError('snapshot_mismatch',409)
            return bundle
        q=(quote_bundle or self.quote(symbol,refresh)) if spot is None else dict(quote={'symbol':symbol,'last':spot,'updated_at':None},retrieved_at=self.clock().isoformat())
        if not finite(q['quote']['last']) or q['quote']['last']<=0:raise APIError('invalid_spot')
        day=self.today()
        key=('snapshot',symbol,horizon,digest(q),str(day))
        def create():
            dataset=self.data.load(('history',symbol,str(day)),300,lambda:self.provider_call(self.provider.history,symbol,day))
            try:
                s=context_from_dataset(dataset,q['quote']['last'],horizon,q['quote']['updated_at'],q['retrieved_at'])
            except (ValueError,KeyError,TypeError):raise APIError('insufficient_historical_data',503) from None
            bundle=dict(prepared=s,quote=q,source='Public' if spot is None else 'Explicit trade input + Public completed history')
            self.snapshots.put(s['snapshot_id'],bundle,120)
            return bundle
        bundle=self.data.load(key,30,create)
        # Cache hits must not extend the snapshot's absolute lifetime.
        return bundle

    def meta(self,bundle=None,symbol=None,horizon=None,quote=None):
        s=bundle['prepared'] if bundle else None
        q=bundle['quote']['quote'] if bundle else quote or {}
        return dict(schema_version=SCHEMA_VERSION,generated_at=self.clock().isoformat(),source=bundle['source'] if bundle else 'Public',
            symbol=s['dataset']['metadata']['symbol'] if s else symbol,research_session=s['research_date'] if s else None,
            research_close=s['research_close'] if s else None,quote_as_of=q.get('updated_at'),current_spot=q.get('last'),
            observed_session_horizon=s['horizon'] if s else horizon,snapshot_id=s['snapshot_id'] if s else None)

    def envelope(self,evidence,bundle=None,**meta):
        return dict(meta=self.meta(bundle,**meta),evidence=evidence,caveats=CAVEATS)

    def timing(self,quote,legs=()):
        values=([quote.get('updated_at')] if quote is not None else [])+[leg.get(k) for leg in legs for k in ('bid_timestamp','ask_timestamp')]
        ages=[(self.clock()-pd.Timestamp(v).to_pydatetime()).total_seconds() for v in values if stamp(v)]
        return dict(timestamps_incomplete=any(not stamp(v) for v in values),
            oldest_quote_age_seconds=max(ages) if ages else None,
            stale_quote=any(age>900 for age in ages),future_timestamp=any(age < -60 for age in ages),
            note='Last available quotes; delay/market-close status is unverified. Older than 15 minutes is flagged, not silently refreshed.')

    def validate_legs(self,short,long,kind,symbol,expiration):
        width=short['strike']-long['strike'] if kind=='put' else long['strike']-short['strike']
        if width<=0:raise APIError('invalid_vertical_orientation')
        for leg in (short,long):
            if leg.get('type')!=kind.title():raise APIError('contract_mismatch')
            if not all(finite(leg.get(k)) and leg[k]>=0 for k in ('bid','ask')):raise APIError('missing_quote')
            if leg['ask']<leg['bid']:raise APIError('crossed_market')
            contract=leg.get('contract')
            parsed=re.fullmatch(r'([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})',contract or '')
            if not parsed:raise APIError('contract_unavailable',404)
            root,day,side,strike=parsed.groups()
            if root!=symbol or day!=date.fromisoformat(expiration).strftime('%y%m%d') or side!=('P' if kind=='put' else 'C') or int(strike)/1000!=leg['strike']:
                raise APIError('contract_mismatch')
        credit=short['bid']-long['ask']
        if credit<=0:raise APIError('nonpositive_natural_credit')
        if credit>=width:raise APIError('invalid_vertical_credit')
        return credit

    def exact_trade(self,symbol,expiration,kind,short_strike,long_strike,horizon,refresh=False):
        symbol=symbol_value(symbol);horizon_value(horizon);expiration=self.expiration(expiration)
        if kind not in ('put','call'):raise APIError('invalid_option_type')
        if not all(finite(v) and v>0 for v in (short_strike,long_strike)):raise APIError('invalid_strike')
        if (short_strike-long_strike if kind=='put' else long_strike-short_strike)<=0:raise APIError('invalid_vertical_orientation')
        q=self.quote(symbol,refresh);chain=self.chain(symbol,expiration,refresh)
        pool=chain['chain']['puts' if kind=='put' else 'calls']
        matches=[[l for l in pool if l.get('strike')==strike] for strike in (short_strike,long_strike)]
        if any(len(m)!=1 for m in matches):raise APIError('contract_unavailable',404)
        short,long=(m[0] for m in matches)
        credit=self.validate_legs(short,long,kind,symbol,expiration)
        trade=dict(symbol=symbol,expiration=expiration,strategy='Bull put spread' if kind=='put' else 'Bear call spread',
            spot=q['quote']['last'],stock_basis=q['quote']['last'],credit=credit,shares=0,fees=0,source='Public natural quote proxy',
            legs=[{**short,'qty':-1},{**long,'qty':1}])
        # snapshot reuses the exact cached underlying quote, not a new underlying request.
        bundle=self.snapshot(symbol,horizon,quote_bundle=q)
        if bundle['quote']!=q:raise APIError('snapshot_mismatch',409)
        return bundle,trade,dict(underlying=q,chain_retrieved_at=chain['retrieved_at'],chain_quality=chain['quality'],short_contract=short,long_contract=long,
            pricing_method='short bid minus long ask; hypothetical natural fill',timing=self.timing(q['quote'],[short,long]))

    def manual_trade(self,req):
        symbol=symbol_value(req.symbol);horizon_value(req.horizon);expiration=self.expiration(req.expiration)
        legs=[l.model_dump() for l in req.legs]
        short=[l for l in legs if l['qty']==-1];long=[l for l in legs if l['qty']==1]
        if len(short)!=1 or len(long)!=1 or short[0]['type']!=long[0]['type']:raise APIError('invalid_vertical_orientation')
        width=short[0]['strike']-long[0]['strike'] if short[0]['type']=='Put' else long[0]['strike']-short[0]['strike']
        if width<=0:raise APIError('invalid_vertical_orientation')
        if req.credit>=width:raise APIError('invalid_vertical_credit')
        return dict(symbol=symbol,expiration=expiration,spot=req.spot,stock_basis=req.spot,credit=req.credit,
            legs=legs,shares=0,fees=0,strategy='Explicit vertical credit spread',source='Explicit user input; no quote inferred')

    def research(self,bundle,trade,method='tolerance',**friction):
        s=bundle['prepared'];dataset=s['dataset']
        try:
            r=research_workspace(dataset['features'][['date','symbol','open','high','low','close']],trade,
                dataset['metadata']['audit']['completed_before'],s['horizon'],method,dataset['metadata'],prepared=s,**friction)
        except (ValueError,KeyError,TypeError):raise APIError('invalid_research_context') from None
        if not r['evidence']['economics']['net_summary']['n']:raise APIError('insufficient_analog_sample')
        return r

    def evidence(self,result,trade):
        e=result['evidence'];stats=e['threshold']['summary'];economics=e['economics'];net=economics['net_summary']
        short=next(leg for leg in trade['legs'] if leg['qty']==-1)
        long=next(leg for leg in trade['legs'] if leg['qty']==1)
        analysis=economics['trade_analysis']
        return dict(context=e['context'],expiration=trade['expiration'],short_strike=short['strike'],long_strike=long['strike'],
            credit=trade['credit'],pricing_method=trade.get('source'),max_profit=analysis['max_profit'],max_loss=analysis['max_loss'],
            breakeven=analysis['breakevens'],return_on_risk=analysis['return_on_risk'],
            historical_terminal_survival=stats['survival_frequency'],
            historical_touch_breach=stats['touch_frequency'],historical_finish_beyond=stats['terminal_breach_frequency'],
            historical_terminal_equality=stats['equality_frequency'],positive_payoff_frequency=net['positive_frequency'],
            scenario_expected_payoff=net['expected_payoff'],EV_max_risk=net['expected_payoff_on_max_risk'],
            profit_factor=net['profit_factor'],profit_factor_unbounded=net['profit_factor']==float('inf'),analog_N=net['n'],
            threshold=stats,threshold_non_overlapping=e['threshold']['non_overlapping_summary'],economics=net,
            economics_non_overlapping=economics['non_overlapping_net_summary'],robustness=result['robustness'],
            levels=result['levels'],distributions=result.get('distributions'),
            required_credit=required_credits(trade,economics),
            provenance=dict(ohlc_sha256=result['provenance']['ohlc_sha256'],research_date=result['provenance']['research_date'],
                completed_before=result['provenance']['completed_before'],analog_config=result['primary']['config'],
                audit=result['provenance']['audit'],engine_version=result['version'],payoff_version=economics['config']['version']))

    def scan(self,symbol,strategy,expiration,dte_min,dte_max,horizon,max_distance,min_credit,max_candidates,width,refresh=False):
        symbol=symbol_value(symbol);horizon_value(horizon)
        if dte_min>dte_max:raise APIError('invalid_dte_range')
        exps=[self.expiration(expiration)] if expiration else [e for e in self.expirations(symbol)['expirations'] if dte_min<=(date.fromisoformat(e)-self.today()).days<=dte_max]
        if not exps:raise APIError('expiration_unavailable',404)
        if len(exps)>5:raise APIError('scan_scope_too_large')
        if refresh:self.quote(symbol,True)
        bundle=self.snapshot(symbol,horizon);s=bundle['prepared'];spot=s['current_spot'];rows=[];chains=[];excluded=[]
        if s['analog']['analogs'].empty:raise APIError('insufficient_analog_sample')
        for expiry in exps:
            c=self.chain(symbol,expiry,refresh);chains.append(c)
            clean=dict(c['chain']);clean['puts']=[];clean['calls']=[]
            for side,kind in [('puts','put'),('calls','call')]:
                contracts=c['chain'][side]
                counts={}
                for l in contracts:
                    k=str(l.get('strike'));counts[k]=counts.get(k,0)+1
                for leg in contracts:
                    if counts[str(leg.get('strike'))]>1:
                        excluded.append(dict(expiration=expiry,code='ambiguous_contract'));continue
                    # Generator handles invalid markets; exclude invalid identity records up front.
                    if not isinstance(leg.get('contract'),str) or not all(finite(leg.get(k)) for k in ('strike','bid','ask')):
                        excluded.append(dict(expiration=expiry,code='missing_quote'));continue
                    clean[side].append(leg)
            dte=(date.fromisoformat(expiry)-self.today()).days
            generated=generate(clean,spot,max(dte,.25)/365,None,width=width,fee=0,pricing='Natural',as_of=self.today(),
                min_net_credit=min_credit*100,max_short_distance=max_distance)
            for row in generated:
                kind='put' if row['strategy']=='Bull put spread' else 'call' if row['strategy']=='Bear call spread' else None
                if kind is None or strategy not in ('both','pcs' if kind=='put' else 'ccs'):continue
                try:self.validate_legs(row['legs'][0],row['legs'][1],kind,symbol,expiry)
                except APIError as exc:
                    excluded.append(dict(expiration=expiry,code=exc.code));continue
                row.update(symbol=symbol,source='Public natural quote proxy',dte=dte)
                rows.append(row)
        total=len(rows);rows=rows[:max_candidates]  # Existing generator order; no score or sorting.
        enriched=annotate_candidates(rows,s,symbol)
        sid='s_'+digest(dict(snapshot=s['snapshot_id'],chains=chains,strategy=strategy,expirations=exps,
            horizon=horizon,distance=max_distance,credit=min_credit,width=width,limit=max_candidates))[:32]
        candidates=[];stored={}
        for index,row in enumerate(enriched):
            cid=sid+'.'+str(index)+'_'+digest(row)[:16];stored[cid]=row
            context=row['research_context'];stat=context['threshold_statistics'];ev=scenario_economics(s['analog'],row,horizon)
            net=ev['net_summary'];analysis=ev['trade_analysis']
            candidates.append(dict(candidate_id=cid,symbol=symbol,strategy=row['strategy'],expiration=row['expiration'],DTE=row['dte'],
                short_strike=row['legs'][0]['strike'],long_strike=row['legs'][1]['strike'],credit=row['credit'],
                max_profit=analysis['max_profit'],max_loss=analysis['max_loss'],breakeven=analysis['breakevens'],return_on_risk=analysis['return_on_risk'],
                distance_from_spot_pct=context['strike_distance_pct'],distance_from_spot_ATR=context['strike_distance_atr'],
                nearest_structural_zone=context['nearest_zone'],structural_relationship=context['structural_position'],
                historical_terminal_survival=stat['survival_frequency'],historical_touch_breach=stat['touch_frequency'],
                historical_finish_beyond=stat['terminal_breach_frequency'],historical_scenario_EV=net['expected_payoff'],
                EV_max_risk=net['expected_payoff_on_max_risk'],positive_payoff_frequency=net['positive_frequency'],analog_N=net['n'],
                quote_timestamps=[{k:leg.get(k) for k in ('contract','bid_timestamp','ask_timestamp')} for leg in row['legs']],
                timing=self.timing(bundle['quote']['quote'],row['legs']),required_credit=required_credits(row,ev)))
        existing=self.scans.get(sid)
        if existing is None:self.scans.put(sid,dict(bundle=bundle,candidates=stored),120)
        return self.envelope(dict(scan_id=sid,candidates=candidates,total_generated=total,truncated=total>max_candidates,
            excluded=excluded,chains_retrieved_at=[c['retrieved_at'] for c in chains],snapshot_valid_seconds=120,
            ordering='Existing premium generator order, capped from the front; no ranking or recommendation.'),bundle)

    def candidate(self,candidate_id):
        if not re.fullmatch(r's_[0-9a-f]{32}\.\d+_[0-9a-f]{16}',candidate_id):raise APIError('invalid_candidate_id',404)
        scan=self.scans.get(candidate_id.split('.')[0])
        if scan is None:raise APIError('stale_snapshot',410)
        trade=scan['candidates'].get(candidate_id)
        if trade is None:raise APIError('invalid_candidate_id',404)
        r=self.research(scan['bundle'],trade)
        result=self.envelope(self.evidence(r,trade),scan['bundle'])
        result['evidence'].update(candidate_id=candidate_id,quote_legs=trade['legs'],timing=self.timing(scan['bundle']['quote']['quote'],trade['legs']))
        return result
