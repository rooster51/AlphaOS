"""Descriptive journal analytics over captured records only; no market-data calls."""
from collections import Counter, defaultdict
from datetime import date, datetime
import json
from statistics import mean, median
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field
from .contracts import APIError
from .positions import PositionStore
from .service import finite, NY

VERSION = 'alphaos-journal-v1'
State = Literal['THESIS_INTACT','UNDER_PRESSURE','BOUNDARY_BREACHED']
Group = Literal['symbol','strategy','entry_dte','dte_bucket','entry_time_bucket','exit_reason',
    'entry_regime','entry_structure','last_monitor_state','hold_bucket','recorded_short_breach']
CAVEATS = [
    'Actual results are user-declared fills, not broker-verified; fees are excluded.',
    'Realized Expectancy Per Recorded Trade is the mean of actual recorded P/L, not Historical Scenario EV or a forecast.',
    'Trades and repeated/overlapping observations are not independent evidence. No statistical inference or causality is implied.',
    'Monitoring is sampled manual refresh history, not a continuous path. Missing history is unknown, not no breach.',
    'Entry evidence was captured at recording time; backdated entry timestamps do not reconstruct past market context.',
    'Small samples are descriptive only; no rankings, probabilities of future profit or recommendations.'
]


class JournalFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: Literal['SPY','QQQ','SPX','XSP']|None = None
    strategy: Literal['PCS','CCS']|None = None
    expiration: date|None = None
    dte_min: int|None = Field(default=None,ge=0)
    dte_max: int|None = Field(default=None,ge=0)
    date_from: date|None = None
    date_to: date|None = None
    date_basis: Literal['entry','close'] = 'close'
    entry_regime: str|None = Field(default=None,max_length=100)
    entry_structure: str|None = Field(default=None,max_length=100)
    exit_reason: str|None = Field(default=None,max_length=100)
    monitor_state: State|None = None
    short_breached: bool|None = None
    breakeven_breached: bool|None = None
    exit_basis: Literal['actual','estimated','unknown']|None = None

    def check(self):
        if self.date_from and self.date_to and self.date_from>self.date_to:
            raise APIError('invalid_journal_date_range')
        if self.dte_min is not None and self.dte_max is not None and self.dte_min>self.dte_max:
            raise APIError('invalid_journal_dte_range')


class JournalPage(JournalFilters):
    limit: int = Field(default=20,ge=1,le=100)
    offset: int = Field(default=0,ge=0)


class PerformanceQuery(JournalFilters):
    group_by: Group|None = None


def instant(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def metric(values, fn=mean):
    values = [v for v in values if finite(v)]
    return dict(value=fn(values) if values else None,n=len(values))


def observed_history(position, events):
    entry_at = instant(position['entry_timestamp'])
    close_at = instant(position['close']['timestamp']) if position.get('close') else None
    monitors = [e for e in events if e['kind']=='monitor']
    eligible = [e for e in monitors if instant(e['observed_at'])>=entry_at and
        (close_at is None or instant(e['observed_at'])<=close_at)]
    eligible.sort(key=lambda e:(instant(e['observed_at']),e['sequence']))
    marks=[];states=[];boundaries=[];transitions=[];previous=None
    for event in eligible:
        payload=event['payload'];current=payload['current_snapshot'];state=payload['monitoring_state']
        # Validated estimates only. Raw stale/crossed quotes never become excursions.
        if not current.get('errors') and finite(current.get('estimated_pl')):
            marks.append(current['estimated_pl'])
        descriptor=state.get('state')
        if descriptor:
            states.append(descriptor)
            if previous and previous!=descriptor:
                transitions.append(dict(from_state=previous,to_state=descriptor,observed_at=event['observed_at'],
                    note='Transition between recorded observations; intervening path is unknown.'))
        previous=descriptor  # Missing assessments break the observed transition chain.
        if current.get('live_underlying'):
            boundaries.append(state.get('breached_boundaries',[]))
    counts=Counter(states)
    best=max(marks) if marks else None;worst=min(marks) if marks else None
    return dict(recorded_monitor_count=len(monitors),eligible_monitor_count=len(eligible),
        excluded_outside_declared_holding_period=len(monitors)-len(eligible),
        valid_valuation_observations=len(marks),boundary_observations=len(boundaries),state_observations=len(states),
        recorded_short_breach=any('short_strike' in b for b in boundaries) if boundaries else None,
        recorded_breakeven_breach=any('breakeven' in b for b in boundaries) if boundaries else None,
        under_pressure_observations=counts['UNDER_PRESSURE'] if states else None,
        boundary_breached_observations=counts['BOUNDARY_BREACHED'] if states else None,
        state_counts=dict(counts),last_monitor_state=states[-1] if states else None,transitions=transitions,
        best_recorded_estimated_pl=best,worst_recorded_estimated_pl=worst,
        recorded_mfe=max(0,best) if best is not None else None,
        recorded_mae=min(0,worst) if worst is not None else None,
        excursion_basis='Positive/negative components of best/worst valid recorded P/L estimates relative to declared entry credit; not continuous-path excursions.',
        history_status='recorded_observations' if eligible else 'not_captured_during_declared_holding_period')


def trade_metrics(p, events):
    entry_at=instant(p['entry_timestamp']);local=entry_at.astimezone(NY)
    close=p.get('close');close_at=instant(close['timestamp']) if close else None
    snapshot=p.get('entry_snapshot',{});context=snapshot.get('captured_context') or {}
    historical=snapshot.get('historical_evidence') or {}
    basis=close.get('exit_basis','actual') if close else None
    # Legacy Phase 10B closures required explicit user-declared amounts.
    actual=close.get('declared_pl') if close and basis=='actual' and finite(close.get('amount')) else None
    estimate=close.get('estimated_pl') if close and basis=='estimated' else None
    quantity=p.get('quantity');maximum=p.get('max_profit_at_entry');risk=p.get('max_loss_at_entry')
    dte=(date.fromisoformat(p['expiration'])-local.date()).days
    hour=local.hour+local.minute/60
    bucket='opening_0930_1030' if 9.5<=hour<10.5 else 'midday_1030_1400' if 10.5<=hour<14 else 'late_1400_1600' if 14<=hour<16 else 'outside_0930_1600'
    hold=(close_at-entry_at).total_seconds() if close_at else None
    history=observed_history(p,events)
    best=history['best_recorded_estimated_pl']
    reached=best>=maximum*.5 if finite(best) and finite(maximum) and maximum>0 else None
    return dict(position_id=p['position_id'],symbol=p['symbol'],strategy=p['strategy'],expiration=p['expiration'],
        short_strike=p['short_strike'],long_strike=p['long_strike'],width=p['width'],quantity=quantity,
        entry_timestamp=p['entry_timestamp'],entry_date=local.date().isoformat(),entry_credit=p['entry_credit'],
        entry_dte=dte,dte_bucket='0DTE' if dte==0 else '1DTE+' if dte>0 else 'invalid',entry_time_bucket=bucket,
        entry_regime=context.get('regime'),entry_structure=context.get('completed_session_ema_structure'),
        entry_context_basis='Frozen completed-session evidence captured at recording time; not reconstructed execution-time context.',
        research_snapshot_id=historical.get('advanced_research',{}).get('snapshot_id'),
        candidate_id=historical.get('trade_snapshot',{}).get('candidate_id'),
        closed_timestamp=close['timestamp'] if close else None,
        closed_date=close_at.astimezone(NY).date().isoformat() if close_at else None,
        exit_basis=basis,exit_amount=close.get('amount') if close else None,
        exit_cashflow=close.get('cashflow') if close else None,exit_reason=close.get('exit_reason') if close else None,
        realized_pl=actual,estimated_exit_pl=estimate,
        realized_pl_per_spread=actual/quantity if finite(actual) and finite(quantity) and quantity>0 else None,
        percent_max_profit_captured=100*actual/maximum if finite(actual) and finite(maximum) and maximum>0 else None,
        percent_defined_risk_realized=100*actual/risk if finite(actual) and finite(risk) and risk>0 else None,
        hold_seconds=hold,hold_bucket=None if hold is None else 'under_30_minutes' if hold<1800 else '30_to_120_minutes' if hold<7200 else '120_minutes_plus',
        reached_50_percent_in_recorded_marks=reached,
        best_recorded_estimate_minus_realized=best-actual if finite(best) and finite(actual) else None,
        **history)


def summary(rows):
    realized=[r for r in rows if finite(r['realized_pl'])]
    pnl=[r['realized_pl'] for r in realized]
    winners=[v for v in pnl if v>0];losers=[v for v in pnl if v<0]
    def values(key, cohort=rows):return [r[key] for r in cohort]
    def frequency(key):
        known=[r[key] for r in rows if r[key] is not None]
        return dict(value=100*sum(known)/len(known) if known else None,n=len(known),recorded_true=sum(known),missing_n=len(rows)-len(known))
    pressure=[r['under_pressure_observations']>0 for r in rows if r['under_pressure_observations'] is not None]
    giveback=[r for r in realized if r['reached_50_percent_in_recorded_marks'] is True]
    return dict(n_closed=len(rows),n_realized=len(realized),n_estimated=sum(r['exit_basis']=='estimated' for r in rows),
        n_missing_actual=len(rows)-len(realized),small_sample=len(realized)<30,small_sample_threshold=30,
        small_sample_note='Below 30 actual recorded outcomes is flagged for visibility; 30 is not a statistical sufficiency threshold.',
        wins=len(winners),losses=len(losers),flat_trades=sum(v==0 for v in pnl),
        realized_win_rate=dict(value=100*len(winners)/len(pnl) if pnl else None,n=len(pnl)),
        cumulative_realized_pl=metric(pnl,sum),average_realized_pl=metric(pnl),median_realized_pl=metric(pnl,median),
        average_winner=metric(winners),average_loser=metric(losers),
        payoff_ratio=dict(value=mean(winners)/abs(mean(losers)) if winners and losers else None,
            n=len(winners)+len(losers),winner_n=len(winners),loser_n=len(losers)),
        realized_expectancy_per_recorded_trade=dict(**metric(pnl),label='Realized Expectancy Per Recorded Trade'),
        average_hold_seconds=metric(values('hold_seconds')),median_hold_seconds=metric(values('hold_seconds'),median),
        average_entry_credit=metric(values('entry_credit')),average_percent_max_profit_captured=metric(values('percent_max_profit_captured')),
        short_strike_breach_frequency=frequency('recorded_short_breach'),breakeven_breach_frequency=frequency('recorded_breakeven_breach'),
        under_pressure_frequency=dict(value=100*sum(pressure)/len(pressure) if pressure else None,n=len(pressure),missing_n=len(rows)-len(pressure)),
        after_recorded_50_percent=dict(n=len(giveback),
            best_estimate_minus_realized=metric(values('best_recorded_estimate_minus_realized',giveback)),
            note='Signed difference between best recorded estimate and actual recorded result, conditional on a sampled mark reaching 50% of entry max profit. Not continuous giveback or causal evidence about holding longer.'),
        captured_context_counts=dict(regime=sum(r['entry_regime'] is not None for r in rows),
            completed_session_structure=sum(r['entry_structure'] is not None for r in rows)))


class TradeJournal:
    def __init__(self, store=None):self.store=store or PositionStore()

    def events(self, position_id=None):
        with self.store.connect() as db:
            return self._events(db,position_id)

    @staticmethod
    def _events(db, position_id=None):
        rows=db.execute('SELECT sequence,event_id,position_id,kind,observed_at,recorded_at,payload_json FROM position_events'
            + (' WHERE position_id=?' if position_id else '')+' ORDER BY sequence',
            (str(position_id),) if position_id else ()).fetchall()
        return [dict(sequence=r[0],event_id=r[1],position_id=r[2],kind=r[3],observed_at=r[4],recorded_at=r[5],payload=json.loads(r[6])) for r in rows]

    def rows(self, filters):
        filters.check()
        with self.store.connect() as db:
            db.execute('BEGIN')  # One consistent view of closures and their events.
            stored=db.execute('SELECT entry_json,close_json FROM positions WHERE close_json IS NOT NULL').fetchall()
            captured_events=self._events(db)
        events=defaultdict(list)
        for event in captured_events:events[event['position_id']].append(event)
        result=[]
        for entry,closed in stored:
            p=dict(**json.loads(entry),close=json.loads(closed))
            r=trade_metrics(p,events[p['position_id']])
            if any(getattr(filters,k) is not None and r[k]!=getattr(filters,k) for k in
                ('symbol','strategy','entry_regime','entry_structure','exit_reason','exit_basis')):continue
            if filters.expiration and r['expiration']!=str(filters.expiration):continue
            if filters.dte_min is not None and r['entry_dte']<filters.dte_min:continue
            if filters.dte_max is not None and r['entry_dte']>filters.dte_max:continue
            day=date.fromisoformat(r['entry_date'] if filters.date_basis=='entry' else r['closed_date'])
            if filters.date_from and day<filters.date_from:continue
            if filters.date_to and day>filters.date_to:continue
            if filters.monitor_state and not r['state_counts'].get(filters.monitor_state):continue
            if filters.short_breached is not None and r['recorded_short_breach'] is not filters.short_breached:continue
            if filters.breakeven_breached is not None and r['recorded_breakeven_breach'] is not filters.breakeven_breached:continue
            result.append(r)
        return sorted(result,key=lambda r:(instant(r['closed_timestamp']),r['position_id']),reverse=True)

    def journal(self, filters, limit=20, offset=0):
        rows=self.rows(filters)
        return dict(schema_version=VERSION,n_closed=len(rows),trades=rows[offset:offset+limit],limit=limit,offset=offset,
            next_offset=offset+limit if offset+limit<len(rows) else None,filters=filters.model_dump(mode='json'),caveats=CAVEATS)

    def review(self, position_id, event_limit=100, event_offset=0):
        with self.store.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT entry_json,close_json FROM positions WHERE id=?',(str(position_id),)).fetchone()
            if not row:raise APIError('position_not_found',404)
            p=dict(**json.loads(row[0]),close=json.loads(row[1]) if row[1] else None,status='closed' if row[1] else 'active')
            events=self._events(db,position_id)
        return dict(schema_version=VERSION,position_id=p['position_id'],status=p['status'],
            entry_record={k:v for k,v in p.items() if k not in ('close','status')},
            monitoring_timeline=events[event_offset:event_offset+event_limit],event_count=len(events),
            next_event_offset=event_offset+event_limit if event_offset+event_limit<len(events) else None,
            outcome=p['close'],metrics=trade_metrics(p,events),caveats=CAVEATS,
            note='Entry, sampled monitoring history, and declared closure are separate evidence layers. Legacy events are never backfilled.')

    def performance(self, filters, group_by=None):
        rows=self.rows(filters);groups=defaultdict(list)
        if group_by:
            for row in rows:groups[row[group_by]].append(row)
        running=0;curve=[]
        for row in reversed(rows):
            if finite(row['realized_pl']):
                running+=row['realized_pl']
                curve.append(dict(position_id=row['position_id'],closed_timestamp=row['closed_timestamp'],
                    realized_pl=row['realized_pl'],cumulative_realized_pl=running,n=len(curve)+1))
        return dict(schema_version=VERSION,filters=filters.model_dump(mode='json'),summary=summary(rows),group_by=group_by,
            groups=[dict(value=k,summary=summary(v)) for k,v in sorted(groups.items(),key=lambda kv:str(kv[0]))],
            cumulative_realized_series=curve,caveats=CAVEATS,
            ordering='Groups sorted by label only; not ranked by performance. Trade counts, not monitoring ticks, are the performance sample unit.')


def register_journal(router,respond):
    @router.get('/journal',operation_id='get_trade_journal')
    def get_trade_journal(query: Annotated[JournalPage,Query()]):
        return respond(TradeJournal().journal(JournalFilters(**query.model_dump(exclude={'limit','offset'})),query.limit,query.offset))

    @router.get('/journal/performance',operation_id='get_trade_performance')
    def get_trade_performance(query: Annotated[PerformanceQuery,Query()]):
        return respond(TradeJournal().performance(JournalFilters(**query.model_dump(exclude={'group_by'})),query.group_by))

    @router.get('/journal/{position_id}',operation_id='get_trade_review')
    def get_trade_review(position_id: UUID,event_limit: int=Query(100,ge=1,le=500),event_offset: int=Query(0,ge=0)):
        return respond(TradeJournal().review(position_id,event_limit,event_offset))
