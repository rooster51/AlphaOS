from copy import deepcopy
from datetime import datetime,timezone
import json
import sqlite3
from uuid import uuid4
from unittest.mock import Mock

import pytest
from alphaos_api.contracts import APIError
from alphaos_api.journal import TradeJournal,JournalFilters
from alphaos_api.positions import PositionStore,PositionMonitor,EntryRequest,CloseRequest
from test_api_hardening import env
from test_positions import entry,record,monitor,position_db


@pytest.fixture
def store(position_db):return PositionStore(position_db)


def seed(store,**changes):
    req=EntryRequest(**entry(**changes));p=req.model_dump(mode='json')
    width=abs(req.short_strike-req.long_strike)
    p.update(position_id=str(uuid4()),width=width,contract_multiplier=100,
        max_profit_at_entry=req.entry_credit*100*req.quantity,max_loss_at_entry=(width-req.entry_credit)*100*req.quantity,
        breakeven_at_entry=req.short_strike+(-req.entry_credit if req.strategy=='PCS' else req.entry_credit),
        contracts=['fixture-short','fixture-long'],entry_snapshot=dict(captured_at=req.entry_timestamp.isoformat(),historical_evidence=None,
            captured_context=dict(regime='RANGE',completed_session_ema_structure='mixed')))
    return store.insert(req,p)


def close(store,p,amount=.07,**changes):
    service=Mock();service.clock.return_value=datetime(2026,9,27,15,tzinfo=timezone.utc)
    values=dict(amount=amount,timestamp='2026-09-24T16:00:00Z');values.update(changes)
    return PositionMonitor(service,store).close(p['position_id'],CloseRequest(**values))


def observe(store,p,pl,state='THESIS_INTACT',at='2026-09-24T15:00:00Z',boundaries=(),errors=(),live=True):
    current=dict(captured_at=at,estimated_pl=pl,errors=list(errors),live_underlying=live,
        underlying=dict(quote=dict(last=100)),estimated_close_debit=.1,spread_midpoint=.09,short_delta=-.2)
    status=dict(state=state,breached_boundaries=list(boundaries),assessment_complete=not errors)
    return store.append_monitor(p['position_id'],current,status,at)


@pytest.mark.parametrize('strategy,short,long',[('PCS',99,98),('CCS',101,102)])
def test_closed_actual_metrics(store,strategy,short,long):
    p=seed(store,strategy=strategy,short_strike=short,long_strike=long,quantity=3)
    close(store,p,.07,exit_reason='profit_target',user_note='Declared close')
    review=TradeJournal(store).review(p['position_id']);m=review['metrics']
    assert m['realized_pl']==pytest.approx(84)
    assert m['realized_pl_per_spread']==pytest.approx(28)
    assert m['percent_max_profit_captured']==pytest.approx(80)
    assert m['percent_defined_risk_realized']==pytest.approx(84/195*100)
    assert m['hold_seconds']==7200 and m['entry_dte']==1
    assert m['exit_reason']=='profit_target'
    assert review['outcome']['user_note']=='Declared close'
    assert review['entry_record']['entry_snapshot']==p['entry_snapshot']


@pytest.mark.parametrize('basis,amount',[('estimated',.07),('unknown',None)])
def test_nonactual_exits_never_realized(store,basis,amount):
    p=seed(store);close(store,p,amount,exit_basis=basis)
    j=TradeJournal(store);row=j.journal(JournalFilters())['trades'][0]
    assert row['realized_pl'] is None and row['percent_max_profit_captured'] is None
    if basis=='estimated':assert row['estimated_exit_pl']==pytest.approx(56)
    else:assert row['estimated_exit_pl'] is None
    s=j.performance(JournalFilters())['summary']
    assert s['n_closed']==1 and s['n_realized']==0 and s['n_missing_actual']==1
    assert s['realized_win_rate']==dict(value=None,n=0)
    assert s['cumulative_realized_pl']==dict(value=None,n=0)


@pytest.mark.parametrize('values',[dict(amount=None),dict(amount=.1,exit_basis='unknown'),dict(amount=None,exit_basis='estimated')])
def test_invalid_fill_classification(values):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):CloseRequest(timestamp='2026-09-24T16:00:00Z',**values)


def test_sampled_excursions_breaches_transitions_and_giveback(store):
    p=seed(store)
    observe(store,p,40,at='2026-09-24T14:10:00Z')
    observe(store,p,10,'UNDER_PRESSURE',at='2026-09-24T14:20:00Z')
    observe(store,p,-80,'BOUNDARY_BREACHED',at='2026-09-24T14:30:00Z',boundaries=['short_strike','breakeven'])
    observe(store,p,999,'UNDER_PRESSURE',at='2026-09-24T14:40:00Z',errors=['stale'],live=False)
    close(store,p,.3)
    r=TradeJournal(store).review(p['position_id']);m=r['metrics']
    assert m['eligible_monitor_count']==4 and m['valid_valuation_observations']==3
    assert m['best_recorded_estimated_pl']==40 and m['worst_recorded_estimated_pl']==-80
    assert m['recorded_mfe']==40 and m['recorded_mae']==-80
    assert m['recorded_short_breach'] is True and m['recorded_breakeven_breach'] is True
    assert m['under_pressure_observations']==2 and m['boundary_breached_observations']==1
    assert m['transitions'][0]['from_state']=='THESIS_INTACT'
    assert m['transitions'][0]['to_state']=='UNDER_PRESSURE'
    s=TradeJournal(store).performance(JournalFilters())['summary']
    assert s['after_recorded_50_percent']['n']==1
    assert s['after_recorded_50_percent']['best_estimate_minus_realized']['value']==pytest.approx(30)
    assert s['short_strike_breach_frequency']['n']==1  # Trade count, not tick count.


def test_missing_monitoring_is_unknown_and_not_false(store):
    p=seed(store);close(store,p)
    r=TradeJournal(store).journal(JournalFilters())['trades'][0]
    for key in ('recorded_mfe','recorded_mae','recorded_short_breach','recorded_breakeven_breach','under_pressure_observations'):
        assert r[key] is None
    assert r['recorded_monitor_count']==0
    assert TradeJournal(store).journal(JournalFilters(short_breached=False))['n_closed']==0


def test_observations_outside_declared_holding_period_excluded(store):
    p=seed(store)
    observe(store,p,100,at='2026-09-24T13:00:00Z')
    observe(store,p,40,at='2026-09-24T15:00:00Z')
    close(store,p,timestamp='2026-09-24T14:30:00Z')
    r=TradeJournal(store).review(p['position_id'])
    assert r['event_count']==3 and r['metrics']['excluded_outside_declared_holding_period']==2
    assert r['metrics']['recorded_mfe'] is None


def test_aggregation_wins_losses_flat_and_missing(store):
    for amount,basis in [(0.1,'actual'),(.6,'actual'),(.35,'actual'),(.01,'estimated'),(None,'unknown')]:
        close(store,seed(store),amount,exit_basis=basis)
    r=TradeJournal(store).performance(JournalFilters());s=r['summary']
    assert s['n_closed']==5 and s['n_realized']==3
    assert (s['wins'],s['losses'],s['flat_trades'])==(1,1,1)
    assert s['realized_win_rate']['value']==pytest.approx(100/3)
    assert s['cumulative_realized_pl']['value']==pytest.approx(0)
    assert s['realized_expectancy_per_recorded_trade']['value']==pytest.approx(0)
    assert s['average_winner']['value']==pytest.approx(50)
    assert s['average_loser']['value']==pytest.approx(-50)
    assert s['payoff_ratio']['value']==pytest.approx(1)
    assert s['average_percent_max_profit_captured']['n']==3
    assert s['small_sample'] and len(r['cumulative_realized_series'])==3
    assert s['short_strike_breach_frequency']['value'] is None


@pytest.mark.parametrize('filters,count',[
    (dict(symbol='QQQ'),1),(dict(symbol='SPY'),2),(dict(strategy='PCS'),2),(dict(strategy='CCS'),1),
    (dict(dte_min=0,dte_max=0),1),(dict(dte_min=1),2),
    (dict(date_from='2026-09-25'),1),(dict(date_to='2026-09-24'),2),
    (dict(date_basis='entry',date_to='2026-09-23'),0),
    (dict(expiration='2026-09-25'),3),(dict(entry_regime='RANGE'),3),(dict(entry_regime='TREND'),0),
    (dict(entry_structure='mixed'),3),(dict(exit_reason='profit_target'),1),
    (dict(monitor_state='UNDER_PRESSURE'),1),(dict(short_breached=True),1),(dict(breakeven_breached=True),0)])
def test_filters(store,filters,count):
    p=seed(store);observe(store,p,0,'UNDER_PRESSURE');close(store,p,exit_reason='profit_target')
    p=seed(store,symbol='QQQ',strategy='CCS',short_strike=101,long_strike=102)
    observe(store,p,-10,'BOUNDARY_BREACHED',boundaries=['short_strike']);close(store,p)
    p=seed(store,entry_timestamp='2026-09-25T14:00:00Z');close(store,p,timestamp='2026-09-25T15:00:00Z')
    j=TradeJournal(store)
    assert j.journal(JournalFilters(**filters))['n_closed']==count
    grouped=j.performance(JournalFilters(),'strategy')['groups']
    assert [g['value'] for g in grouped]==['CCS','PCS']
    assert sum(g['summary']['n_realized'] for g in grouped)==3


def test_pagination_and_review_events(store):
    for _ in range(3):close(store,seed(store))
    j=TradeJournal(store);a=j.journal(JournalFilters(),2,0);b=j.journal(JournalFilters(),2,2)
    assert a['n_closed']==3 and a['next_offset']==2 and b['next_offset'] is None
    assert len({r['position_id'] for r in a['trades']+b['trades']})==3
    p=seed(store);observe(store,p,10);observe(store,p,20);close(store,p)
    r=j.review(p['position_id'],1,0)
    assert r['event_count']==3 and len(r['monitoring_timeline'])==1 and r['next_event_offset']==1
    assert r['metrics']['eligible_monitor_count']==2


def test_append_only_and_closed_race(store):
    p=seed(store);observe(store,p,10)
    for sql in ('UPDATE position_events SET kind=\'close\'','DELETE FROM position_events'):
        with pytest.raises(sqlite3.IntegrityError),store.connect() as db:db.execute(sql)
    close(store,p)
    with pytest.raises(APIError) as exc:observe(store,p,20)
    assert exc.value.code=='position_closed_during_refresh'
    assert len(TradeJournal(store).events(p['position_id']))==2


def test_legacy_migration_restart_and_retry(position_db):
    # Build an actual old-schema file, then remove new fields from a fixture position.
    temporary=PositionStore(str(position_db)+'.seed');p=seed(temporary)
    closed=close(temporary,p)
    frozen={k:v for k,v in p.items() if k not in ('status','close')}
    frozen['entry_snapshot'].pop('captured_context')
    entry_bytes=json.dumps(frozen,indent=1);close_bytes=json.dumps(closed['close'],indent=2)
    with sqlite3.connect(position_db) as db:
        db.execute('CREATE TABLE positions (id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,request_json TEXT NOT NULL,entry_json TEXT NOT NULL,close_json TEXT)')
        db.execute('INSERT INTO positions VALUES (?,?,?,?,?)',(p['position_id'],p['request_id'],'{}',entry_bytes,close_bytes))
    migrated=PositionStore(position_db)
    r=TradeJournal(migrated).review(p['position_id'])
    assert r['event_count']==0 and r['metrics']['entry_regime'] is None
    assert r['metrics']['realized_pl']==pytest.approx(56)
    assert close(migrated,p)['close']==closed['close']
    with migrated.connect() as db:
        assert db.execute('SELECT entry_json,close_json FROM positions').fetchone()==(entry_bytes,close_bytes)
    assert TradeJournal(PositionStore(position_db)).review(p['position_id'])==r


def test_api_monitor_stores_events_and_journal_does_not_research(env,position_db):
    c,provider,_,clock=env;p=record(c);frozen=deepcopy(p['entry_snapshot'])
    r=monitor(c,p);assert r['monitor_event_id']
    provider.reset_mock()
    url='/v1/positions/'+p['position_id']+'/close'
    close_response=c.post(url,json=dict(amount=.07,timestamp=clock().isoformat(),exit_reason='profit_target'))
    assert close_response.status_code==200,close_response.text
    assert c.get('/v1/journal').json()['n_closed']==1
    assert c.get('/v1/journal/performance?group_by=strategy').json()['summary']['n_realized']==1
    review=c.get('/v1/journal/'+p['position_id']).json()
    assert review['event_count']==2 and review['entry_record']['entry_snapshot']==frozen
    assert c.get('/v1/journal',headers={'Authorization':''}).status_code==401
    assert c.get('/v1/journal?limit=0').status_code==422
    assert c.get('/v1/journal?date_from=2026-10-01&date_to=2026-09-01').status_code==422
    assert c.get('/v1/journal?dte_min=2&dte_max=0').status_code==422
    assert c.get('/v1/journal/not-a-uuid').status_code==422
    assert c.get('/v1/journal/'+str(uuid4())).status_code==404
    assert not provider.mock_calls


def test_close_and_event_are_atomic(store):
    p=seed(store)
    with store.connect() as db:
        db.execute("CREATE TRIGGER fail_close_event BEFORE INSERT ON position_events WHEN NEW.kind='close' BEGIN SELECT RAISE(ABORT,'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):close(store,p)
    assert store.get(p['position_id'])['status']=='active'
    assert TradeJournal(store).events(p['position_id'])==[]


def test_actual_credit_exit_and_unknown_quantity(store):
    from alphaos_api.journal import trade_metrics
    p=seed(store);closed=close(store,p,.1,cashflow='credit')
    assert trade_metrics(closed,[])['realized_pl']==pytest.approx(90)
    closed['quantity']=None
    assert trade_metrics(closed,[])['realized_pl_per_spread'] is None


def test_date_timezone_and_unknown_context(store):
    p=seed(store,entry_timestamp='2026-09-25T00:30:00+00:00')
    close(store,p,timestamp='2026-09-25T01:30:00+00:00')
    row=TradeJournal(store).journal(JournalFilters(date_to='2026-09-24'))['trades'][0]
    assert row['entry_dte']==1 and row['entry_date']=='2026-09-24'
    assert row['closed_date']=='2026-09-24' and row['hold_seconds']==3600


def test_empty_performance_and_missing_assessment_breaks_transitions(store):
    j=TradeJournal(store)
    assert j.performance(JournalFilters())['summary']['n_closed']==0
    p=seed(store);observe(store,p,5)
    observe(store,p,None,state=None,at='2026-09-24T15:01:00Z',errors=['unavailable'],live=False)
    observe(store,p,-20,'UNDER_PRESSURE',at='2026-09-24T15:02:00Z')
    close(store,p)
    r=j.review(p['position_id'])['metrics']
    assert r['transitions']==[] and r['recorded_mfe']==5


@pytest.mark.parametrize('basis,amount',[('estimated',.07),('unknown',None)])
def test_nonactual_exit_api(env,position_db,basis,amount):
    c,_,_,clock=env;p=record(c)
    r=c.post('/v1/positions/'+p['position_id']+'/close',json=dict(amount=amount,exit_basis=basis,timestamp=clock().isoformat()))
    assert r.status_code==200,r.text
    assert r.json()['close']['declared_pl'] is None
    assert c.get('/v1/journal/performance').json()['summary']['n_realized']==0


def test_review_uses_one_database_snapshot_during_concurrent_close(store):
    with store.connect() as db:db.execute('PRAGMA journal_mode=WAL')
    p=seed(store)
    class ClosingJournal(TradeJournal):
        injected=False
        def _events(self,db,position_id=None):
            if not self.injected:
                self.injected=True
                close(store,p)  # Another connection commits after the position SELECT.
            return super()._events(db,position_id)
    journal=ClosingJournal(store)
    before=journal.review(p['position_id'])
    assert before['status']=='active' and before['outcome'] is None and before['event_count']==0
    after=journal.review(p['position_id'])
    assert after['status']=='closed' and after['event_count']==1
