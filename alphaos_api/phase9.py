"""Thin service orchestration for Phase 9; original endpoints and engines remain authoritative."""
import re
from modules.symbol_registry import instrument, metadata as instrument_metadata
from modules.unified_trade import build_unified_trade
from modules.price_structure import nearest_levels
from .contracts import APIError
from .service import symbol_value, horizon_value

VERSION='alphaos-symbol-research-v1'


class UnifiedResearch:
    def __init__(self,service):
        self.service=service

    def live_state(self,quote):
        from modules.quote_freshness import freshness
        quality=freshness(quote['quote'],self.service.clock(),quote['retrieved_at'])
        return dict(**quality,current_spot=quote['quote']['last'] if quality['usable_for_live_research'] else None,
            observation_price=quote['quote']['last'],cache=quote.get('cache'))

    def trade(self,bundle,trade,*,candidate_id=None,include_advanced=False):
        r=self.service.research(bundle,trade)
        result=build_unified_trade(r,self.live_state(bundle['quote']),candidate_id=candidate_id,include_advanced=include_advanced)
        result['advanced_research']['snapshot_id']=bundle['prepared']['snapshot_id']
        result['advanced_research']['provider_quotes']=dict(underlying=bundle['quote']['quote'],option_legs=trade['legs'])
        return result

    def candidate(self,candidate_id,include_advanced=False):
        if not re.fullmatch(r's_[0-9a-f]{32}\.\d+_[0-9a-f]{16}',candidate_id):raise APIError('invalid_candidate_id',404)
        scan=self.service.scans.get(candidate_id.split('.')[0])
        if scan is None:raise APIError('stale_snapshot',410)
        trade=scan['candidates'].get(candidate_id)
        if trade is None:raise APIError('invalid_candidate_id',404)
        return self.trade(scan['bundle'],trade,candidate_id=candidate_id,include_advanced=include_advanced)

    def vertical(self,symbol,expiration,option_type,short_strike,long_strike,horizon=3,refresh=False,include_advanced=False):
        bundle,trade,quotes=self.service.exact_trade(symbol,expiration,option_type,short_strike,long_strike,horizon,refresh)
        result=self.trade(bundle,trade,include_advanced=include_advanced)
        result['advanced_research']['provider_quotes']=quotes
        return result

    def run(self,symbol,horizon=3,mode='run',strategy='both',expiration=None,dte_min=1,dte_max=7,
            maximum_candidates=4,minimum_credit=.05,wing_width=None,refresh=False):
        symbol=symbol_value(symbol);horizon_value(horizon)
        wing_width=instrument(symbol).default_wing_width if wing_width is None else wing_width
        service=self.service
        response=dict(instrument=instrument_metadata(symbol),schema_version=VERSION,symbol=symbol,mode=mode,status='complete',stages=[],live_trade_state=None,
            market_snapshot=None,market_structure=None,candidate_scan=None,qualifying_candidates=[],errors=[],
            defaults=dict(observed_session_horizon=horizon,dte_min=dte_min,dte_max=dte_max,expiration=str(expiration) if expiration else None,
                maximum_candidates=maximum_candidates,minimum_credit=minimum_credit,wing_width=wing_width),
            presentation=dict(order='Generator order; not a ranking.',sections=['Data state','Market context and structure','Qualifying candidates','Trade evidence'],
                instruction='Present one concise research workflow. Preserve dates, sample sizes and caveats. Explain any stopped stage; do not select a winner.'),
            caveats=['Historical frequencies are descriptive, not future probabilities.','Observed-session horizon differs from calendar DTE.',
                'Historical scenario EV is not a forecast of future profit or guaranteed expectancy.'])
        try:
            q=service.quote(symbol,refresh)
        except APIError as exc:
            response.update(status='data_unavailable',errors=[dict(stage='data_validation',code=exc.code)])
            return response
        response['live_trade_state']=state=self.live_state(q)
        response['stages'].append('data_validation')
        if not state['usable_for_contextual_research']:
            response.update(status='live_research_stopped',stop_reason=state['freshness_reason'])
            return response
        try:
            bundle=service.snapshot(symbol,horizon,quote_bundle=q)
            s=bundle['prepared'];a=s['analog']
            response['market_snapshot']=dict(research_session=s['research_date'],research_close=s['research_close'],
                market_state=a['target'],analog_config=a['config'],analog_N=len(a['analogs']),snapshot_id=s['snapshot_id'])
            response['market_structure']=dict(atr=s['structure']['atr'],levels=nearest_levels(s['structure']))
            response['stages']+=['market_snapshot','price_structure']
            if not state['usable_for_live_research']:
                response.update(status='context_only',stop_reason=state['freshness_reason'])
                return response
            if mode=='overview':return response
            scan=service.scan(symbol,strategy,expiration,dte_min,dte_max,horizon,.05,minimum_credit,maximum_candidates,wing_width,
                refresh=refresh,snapshot_bundle=bundle)
            response['candidate_scan']=scan['evidence']
            response['stages'].append('candidate_scan')
            if mode=='run':
                for row in scan['evidence']['candidates']:
                    try:response['qualifying_candidates'].append(self.candidate(row['candidate_id']))
                    except APIError as exc:
                        response['errors'].append(dict(stage='candidate_research',candidate_id=row['candidate_id'],code=exc.code))
                response['stages'].append('unified_candidate_research')
            if response['errors']:response['status']='partial'
            response['live_trade_state']=self.live_state(q)
            if not response['live_trade_state']['usable_for_live_research']:
                response.update(status='live_research_stopped',stop_reason='quote_expired_during_workflow',candidate_scan=None,qualifying_candidates=[])
        except APIError as exc:
            response.update(status='partial',errors=[dict(stage='research',code=exc.code)])
        finally:
            response['live_trade_state']=self.live_state(q)
            final=response['live_trade_state']
            if not final['usable_for_live_research']:
                response.update(status='context_only' if final['usable_for_contextual_research'] else 'live_research_stopped',
                    stop_reason=final['freshness_reason'],candidate_scan=None,qualifying_candidates=[])
        return response
