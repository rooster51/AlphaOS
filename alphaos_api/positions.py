"""Owner-local declared positions. No brokerage operations or inferred executions."""
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from contextlib import contextmanager
import json
import os
import re
import sqlite3
import time

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator
from modules.daily_archive import json_value
from modules.option_quote_quality import option_quality
from modules.symbol_registry import instrument
from .contracts import APIError, TradeRequest
from .service import symbol_value, finite, NY


class EntryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    request_id: UUID
    symbol: Literal['SPY', 'QQQ', 'SPX', 'XSP']
    strategy: Literal['PCS', 'CCS']
    expiration: date
    short_strike: float = Field(gt=0)
    long_strike: float = Field(gt=0)
    quantity: int = Field(ge=1, le=10000, strict=True)
    entry_credit: float = Field(gt=0)
    entry_timestamp: AwareDatetime
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def economics(self):
        width = (self.short_strike-self.long_strike) * (1 if self.strategy=='PCS' else -1)
        if not 0 < self.entry_credit < width:
            raise ValueError('Require correctly oriented vertical and credit below width')
        if self.entry_timestamp.astimezone(NY).date() > self.expiration:
            raise ValueError('Entry cannot follow expiration')
        return self


class CloseRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    amount: float|None = Field(default=None,ge=0)
    cashflow: Literal['debit', 'credit'] = 'debit'
    timestamp: AwareDatetime
    exit_basis: Literal['actual','estimated','unknown'] = 'actual'
    exit_reason: Literal['profit_target','risk_management','short_strike_pressure','breakeven_pressure',
        'thesis_changed','expiration','manual_discretionary','other']|None = None
    user_note: str = Field(default='',max_length=2000)

    @model_validator(mode='after')
    def exit_evidence(self):
        if (self.amount is None) != (self.exit_basis=='unknown'):
            raise ValueError('Actual/estimated exits require an explicit amount; unknown exits omit it')
        return self


class PositionStore:
    """Immutable entry JSON; atomic, explicit closure. Separate from OAuth storage."""
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('ALPHAOS_POSITIONS_DB', 'data/active-positions.sqlite3'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS positions (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, request_json TEXT NOT NULL, entry_json TEXT NOT NULL, close_json TEXT)')
            # Additive migration: no rewrites of legacy positions or fabricated events.
            db.execute('''CREATE TABLE IF NOT EXISTS position_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
                position_id TEXT NOT NULL REFERENCES positions(id), kind TEXT NOT NULL,
                observed_at TEXT NOT NULL, recorded_at TEXT NOT NULL, payload_json TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS position_events_position ON position_events(position_id,sequence)')
            for operation in ('UPDATE','DELETE'):
                db.execute(f'''CREATE TRIGGER IF NOT EXISTS position_events_no_{operation.lower()}
                    BEFORE {operation} ON position_events BEGIN SELECT RAISE(ABORT,'Journal events are append-only'); END''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def existing(self, request):
        with self.connect() as db:
            row = db.execute('SELECT id,request_json FROM positions WHERE request_id=?', (str(request.request_id),)).fetchone()
        if row:
            if json.loads(row[1]) != request.model_dump(mode='json'):
                raise APIError('position_request_conflict', 409)
            return self.get(row[0])

    def insert(self, request, entry):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO positions VALUES (?,?,?,?,NULL)',
                (entry['position_id'], str(request.request_id), request.model_dump_json(), json.dumps(json_value(entry), allow_nan=False)))
        return self.existing(request)

    def get(self, position_id):
        with self.connect() as db:
            row = db.execute('SELECT entry_json,close_json FROM positions WHERE id=?', (str(position_id),)).fetchone()
        if not row:
            raise APIError('position_not_found', 404)
        entry = json.loads(row[0])
        return dict(**entry, status='closed' if row[1] else 'active', close=json.loads(row[1]) if row[1] else None)

    def active(self, symbol=None):
        with self.connect() as db:
            rows = db.execute('SELECT id FROM positions WHERE close_json IS NULL ORDER BY rowid DESC').fetchall()
        return [p for row in rows if (p:=self.get(row[0])) and (symbol is None or p['symbol']==symbol)]

    def close(self, position_id, value, recorded_at=None):
        with self.connect() as db:
            changed = db.execute('UPDATE positions SET close_json=? WHERE id=? AND close_json IS NULL',
                (json.dumps(value, allow_nan=False), str(position_id)))
            if changed.rowcount:
                self._event(db,position_id,'close',value['timestamp'],recorded_at or value['timestamp'],value)
        result = self.get(position_id)
        if result['close'] != value:
            raise APIError('position_already_closed', 409)
        return result

    @staticmethod
    def _event(db, position_id, kind, observed_at, recorded_at, payload):
        event_id = str(uuid4())
        db.execute('INSERT INTO position_events (event_id,position_id,kind,observed_at,recorded_at,payload_json) VALUES (?,?,?,?,?,?)',
            (event_id,str(position_id),kind,observed_at,recorded_at,json.dumps(json_value(payload),allow_nan=False)))
        return event_id

    def append_monitor(self, position_id, current, state, recorded_at):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT close_json FROM positions WHERE id=?',(str(position_id),)).fetchone()
            if not row or row[0] is not None:
                raise APIError('position_closed_during_refresh',409)
            return self._event(db,position_id,'monitor',current['captured_at'],recorded_at,
                dict(current_snapshot=current,monitoring_state=state))


def distances(position, spot):
    direction = 1 if position['strategy']=='PCS' else -1
    return {name: direction*(spot-position[key]) for name,key in
        [('short_strike','short_strike'), ('breakeven','breakeven_at_entry'), ('long_strike','long_strike')]}


class PositionMonitor:
    def __init__(self, service, store):
        self.service, self.store = service, store

    def selected(self, position):
        c = self.service.chain(position['symbol'], position['expiration'], refresh=True)
        kind = 'Put' if position['strategy']=='PCS' else 'Call'
        pool = c['chain']['puts' if kind=='Put' else 'calls']
        legs = []
        for index, strike in enumerate((position['short_strike'],position['long_strike'])):
            matches = [l for l in pool if l.get('strike')==strike]
            if len(matches)!=1:
                raise APIError('contract_unavailable', 404)
            leg = matches[0]
            parsed = re.fullmatch(r'([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})', leg.get('contract') or '')
            if not parsed:
                raise APIError('contract_mismatch')
            root, day, side, encoded_strike = parsed.groups()
            if (root not in instrument(position['symbol']).option_roots or leg.get('type')!=kind
                    or day!=date.fromisoformat(position['expiration']).strftime('%y%m%d')
                    or side!=kind[0] or int(encoded_strike)/1000!=strike):
                raise APIError('contract_mismatch')
            if position.get('contracts') and leg['contract']!=position['contracts'][index]:
                raise APIError('contract_identity_changed',409)
            legs.append(leg)
        return legs, c

    def observation(self, p, selected=None):
        now = self.service.clock()
        result = dict(captured_at=now.isoformat(), underlying=None, option_legs=[], errors=[],
            estimated_close_debit=None, spread_midpoint=None, natural_entry_credit=None,
            short_delta=None, distances=None, structure=None,
            pricing_method='Short ask minus long bid; hypothetical natural close debit per share, not an executable fill. Excludes fees. Raw observations are retained; stale/invalid prices are not valued.')
        try:
            q = self.service.quote(p['symbol'], refresh=True)
            result['underlying'] = q
            result['distances'] = distances(p,q['quote']['last'])
        except APIError as exc:
            result['errors'].append(exc.code)
        try:
            legs, chain = selected or self.selected(p)
            result.update(option_legs=legs, chain_quality=chain['quality'],
                consumed_contract_quality=option_quality(legs,now,chain['retrieved_at']))
            valid = all(finite(l.get(k)) and l[k]>=0 for l in legs for k in ('bid','ask'))
            valid = valid and all(l['ask']>=l['bid'] for l in legs)
            if not valid:
                result['errors'].append('missing_or_crossed_option_quotes')
            short,long = legs
            result['short_delta'] = short.get('delta') if finite(short.get('delta')) else None
            if valid:
                raw = short['ask']-long['bid']
                result['raw_close_debit'] = raw
                result['natural_entry_credit'] = short['bid']-long['ask']
                result['raw_spread_midpoint'] = (short['bid']+short['ask']-long['bid']-long['ask'])/2
                if not 0 <= raw <= p['width']:
                    result['errors'].append('spread_quote_outside_payoff_bounds')
                elif result['consumed_contract_quality']['all_contracts_fresh']:
                    result['estimated_close_debit'] = raw
                    result['spread_midpoint'] = result['raw_spread_midpoint']
            if not result['consumed_contract_quality']['all_contracts_fresh']:
                result['errors'].append('option_quotes_not_fresh')
        except APIError as exc:
            result['errors'].append(exc.code)
        q = result['underlying']
        live = bool(q and q['freshness']['usable_for_live_research'])
        if not live:
            result['errors'].append('underlying_not_live')
            result['estimated_close_debit'] = result['spread_midpoint'] = None
        # Only reuse completed-session history already cached by normal research.
        # Monitoring never downloads five years of history or reruns analog research.
        dataset = self.service.data.get(('history',p['symbol'],str(self.service.today())))
        if dataset is not None and q:
            from modules.price_structure import price_structure, nearest_levels
            try:
                structure = price_structure(dataset['features'],anchor_spot=q['quote']['last'])
                result['structure'] = json_value(dict(levels=nearest_levels(structure,1),config=structure['config'],
                    research_close=structure['research_close'],source='Cached completed-session history; no new historical request'))
            except (KeyError, ValueError, TypeError):
                result['structure'] = None
        if result['structure'] is None:
            result['structure_status'] = 'unavailable_without_cached_completed_history'
        result['calendar_dte'] = (date.fromisoformat(p['expiration'])-self.service.today()).days
        result['time_note'] = 'Calendar days only; expiration does not imply closure or verified settlement time.'
        result['live_underlying'] = live
        return result

    def record(self, request):
        existing = self.store.existing(request)
        if existing:
            return existing
        now = self.service.clock()
        if request.entry_timestamp > now:
            raise APIError('future_entry_timestamp')
        p = request.model_dump(mode='json')
        multiplier = instrument(request.symbol).contract_multiplier
        width = abs(request.short_strike-request.long_strike)
        p.update(position_id=str(uuid4()),width=width,contract_multiplier=multiplier,
            max_profit_at_entry=request.entry_credit*multiplier*request.quantity,
            max_loss_at_entry=(width-request.entry_credit)*multiplier*request.quantity,
            breakeven_at_entry=request.short_strike+(-request.entry_credit if request.strategy=='PCS' else request.entry_credit))
        selected = self.selected(p)  # Verify exact identities before persisting a new position.
        p['contracts'] = [l['contract'] for l in selected[0]]
        observed = self.observation(p,selected)
        observed.update(declared_entry_timestamp=p['entry_timestamp'],
            observation_note='Captured at recording time, not reconstructed at the declared execution time. Entry and closure are user declarations, unverified by a broker.',
            historical_evidence=None)
        try:
            from .phase9 import UnifiedResearch
            q = observed['underlying']
            if q is None:
                raise APIError('quote_unavailable')
            bundle = self.service.snapshot(p['symbol'],3,quote_bundle=q)
            req = TradeRequest(symbol=p['symbol'],expiration=p['expiration'],spot=q['quote']['last'],credit=p['entry_credit'],
                legs=[dict(type=l['type'],strike=l['strike'],qty=-1 if i==0 else 1) for i,l in enumerate(selected[0])])
            trade = self.service.manual_trade(req)
            observed['historical_evidence'] = json_value(UnifiedResearch(self.service).trade(bundle,trade))
            from modules.price_structure import nearest_levels
            s = bundle['prepared']
            observed['structure'] = json_value(dict(levels=nearest_levels(s['structure'],1),
                config=s['structure']['config'],research_close=s['research_close'],source='Entry completed-session research'))
            observed['captured_context'] = json_value(dict(completed_session_ema_structure=s['analog']['target'].get('ema_structure'),
                research_session=s['research_date'],regime=None,vwap_relationship=None,
                note='Completed-session context observed at recording time, not reconstructed at the declared entry time. Regime and VWAP were not captured.'))
        except APIError as exc:
            observed['historical_evidence_unavailable'] = exc.code
        p['entry_snapshot'] = observed
        return self.store.insert(request,p)

    def monitor(self, position_id):
        start = time.perf_counter()
        p = self.store.get(position_id)
        if p['status']!='active':
            raise APIError('position_closed',409)
        current = self.observation(p)
        entry = p['entry_snapshot']
        debit = current['estimated_close_debit']
        scale = p['quantity']*p['contract_multiplier']
        pl = p['entry_credit']-debit if debit is not None else None
        current.update(estimated_pl_per_share=pl, estimated_pl=pl*scale if pl is not None else None,
            percent_max_profit_captured=100*pl/p['entry_credit'] if pl is not None else None,
            remaining_max_loss_exposure=(p['width']-debit)*scale if debit is not None else None,
            remaining_loss_definition='Additional theoretical loss from quoted valuation to width at expiration; (width - estimated close debit) * multiplier * quantity. Not entry max loss; excludes fees and assignment effects.')
        def difference(a,b):
            return a-b if finite(a) and finite(b) else None
        def spot(s):
            return s['underlying']['quote']['last'] if s.get('underlying') else None
        changes = dict(underlying_move=difference(spot(current),spot(entry)),
            spread_value_change=difference(debit,entry.get('estimated_close_debit')),
            credit_captured_per_share=pl,short_delta_change=difference(current['short_delta'],entry['short_delta']),
            distance_changes={k:difference((current['distances'] or {}).get(k),(entry['distances'] or {}).get(k)) for k in ('short_strike','breakeven','long_strike')},
            structure=dict(entry=entry.get('structure'),current=current.get('structure')),
            quality=dict(entry=entry['errors'],current=current['errors']),
            elapsed_since_declared_entry_seconds=(self.service.clock()-datetime.fromisoformat(p['entry_timestamp'])).total_seconds(),
            elapsed_since_capture_seconds=(self.service.clock()-datetime.fromisoformat(entry['captured_at'])).total_seconds())
        breaches = [k for k,v in (current['distances'] or {}).items() if v<=0] if current['live_underlying'] else []
        pressure = []
        if current['live_underlying'] and entry.get('live_underlying'):
            for k in ('short_strike','breakeven'):
                before = (entry['distances'] or {}).get(k)
                after = (current['distances'] or {}).get(k)
                if finite(before) and before>0 and finite(after) and after<=before*.5:
                    pressure.append(k+'_buffer_reduced_by_at_least_half')
        if not current['errors'] and not entry['errors'] and finite(current['short_delta']) and finite(entry['short_delta']):
            if abs(current['short_delta'])-abs(entry['short_delta'])>=.10-1e-9:
                pressure.append('absolute_short_delta_increased_at_least_0.10')
        if current['errors'] and not entry['errors']:
            pressure.append('quote_quality_deteriorated')
        state = 'BOUNDARY_BREACHED' if breaches else 'UNDER_PRESSURE' if pressure else None if current['errors'] else 'THESIS_INTACT'
        result = dict(position=p,current_snapshot=current,entry_vs_current=changes,
            monitoring_state=dict(state=state,breached_boundaries=breaches,reasons=pressure,
                assessment_complete=not bool(current['errors']),data_limitations=current['errors'],
                rule_version='explicit-boundaries-and-buffers-v1',note='Descriptive observations only. No recommendation or probability. Boundary equality counts as reached.'),
            monitor_latency_ms=round((time.perf_counter()-start)*1000,2))
        result['monitor_event_id'] = self.store.append_monitor(position_id,current,result['monitoring_state'],self.service.clock().isoformat())
        result['monitor_latency_ms'] = round((time.perf_counter()-start)*1000,2)
        return result

    def close(self, position_id, request):
        p = self.store.get(position_id)
        if not datetime.fromisoformat(p['entry_timestamp']) <= request.timestamp <= self.service.clock():
            raise APIError('invalid_close_timestamp')
        debit = request.amount*(1 if request.cashflow=='debit' else -1) if request.amount is not None else None
        pl = (p['entry_credit']-debit)*p['quantity']*p['contract_multiplier'] if debit is not None else None
        # Preserve exact legacy actual-close shape/idempotency when no new fields supplied.
        value = request.model_dump(mode='json',exclude={'exit_basis','exit_reason','user_note'})
        value.update(signed_close_debit=debit,declared_pl=pl if request.exit_basis=='actual' else None,
            note='User-declared closure; no brokerage verification; excludes fees.')
        if request.exit_basis!='actual':
            value.update(exit_basis=request.exit_basis,estimated_pl=pl if request.exit_basis=='estimated' else None,
                note='User-declared closure without an actual fill; excluded from realized performance.')
        if request.exit_reason is not None:value['exit_reason']=request.exit_reason
        if request.user_note:value['user_note']=request.user_note
        return self.store.close(position_id,value,self.service.clock().isoformat())


def register_positions(router, service, respond):
    def monitor():
        return PositionMonitor(service(),PositionStore())

    @router.post('/positions',operation_id='record_position')
    def record_position(request: EntryRequest):
        return respond(monitor().record(request))

    @router.get('/positions',operation_id='get_active_positions')
    def get_active_positions(symbol: str|None=None):
        positions = monitor().store.active(symbol_value(symbol) if symbol else None)
        return respond(dict(positions=positions,match_count=len(positions),requires_selection=len(positions)>1))

    @router.get('/positions/{position_id}',operation_id='get_position')
    def get_position(position_id: UUID):
        return respond(monitor().store.get(position_id))

    @router.get('/positions/{position_id}/monitor',operation_id='monitor_position')
    def monitor_position(position_id: UUID):
        return respond(monitor().monitor(position_id))

    @router.post('/positions/{position_id}/close',operation_id='close_position')
    def close_position(position_id: UUID,request: CloseRequest):
        return respond(monitor().close(position_id,request))
