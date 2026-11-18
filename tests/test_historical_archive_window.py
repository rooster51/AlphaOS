"""Synthetic immutable archives: coverage assertions are not simulated fills."""
from copy import deepcopy
from datetime import datetime, timedelta
import gzip
import hashlib
import json
from types import SimpleNamespace

from modules.historical_archive_window import read_archive_window

START='2026-11-03T15:00:00+00:00'
END='2026-11-03T15:10:00+00:00'
AS_OF='2026-11-03T16:00:00+00:00'
EXPIRY='2026-11-06'
CONTRACT='SPY261106C00600000'


class Store:
    def __init__(self): self.rows=[]; self.objects={}; self.storage=self
    def table(self,name):
        assert name=='option_snapshots'
        self.filters=[]; self.cap=None
        return self
    def select(self,fields,**kwargs): assert fields=='*' and kwargs==dict(count='exact'); return self
    def eq(self,k,v): self.filters.append((k,'eq',v)); return self
    def gte(self,k,v): self.filters.append((k,'gte',v)); return self
    def lt(self,k,v): self.filters.append((k,'lt',v)); return self
    def order(self,*a,**kw): return self
    def limit(self,n): self.cap=n; return self
    def execute(self):
        rows=self.rows
        for k,op,v in self.filters:
            rows=[r for r in rows if (r.get(k)==v if op=='eq' else
                r.get(k) is not None and (r[k]>=v if op=='gte' else r[k]<v))]
        return SimpleNamespace(data=deepcopy(rows[:self.cap]),count=len(rows))
    def from_(self,bucket): assert bucket=='market-archive'; return self
    def download(self,path): return self.objects[path]
    def add(self,slot=START,symbol='SPY',mutate=lambda p:None):
        stamp=datetime.fromisoformat(slot)
        observed=(stamp+timedelta(seconds=10)).isoformat()
        finish=(stamp+timedelta(seconds=20)).isoformat()
        contract=CONTRACT.replace('SPY',symbol)
        p=dict(schema_version='intraday-archive-v1',provider='Public',symbol=symbol,
            session='2026-11-03',slot_time=slot,observed_at=observed,collection_finished_at=finish,
            underlying=dict(symbol=symbol,last=600,last_timestamp=observed),
            options=dict(schema_version='options-archive-v1',provider='Public',symbol=symbol,
                snapshot_date='2026-11-03',status='complete',received_contract_count=1,
                invalid_expiration_count=0,expiration_failures=[],requested_expirations=[EXPIRY],
                requests=[dict(expiration=EXPIRY,started_at=observed,received_at=finish)],
                collection_started_at=observed,generated_at=finish,
                valid_contracts=[dict(contract=contract,symbol=symbol,expiration=EXPIRY,
                    type='call',strike=600,bid=1,ask=1.02,quote_outcome='SUCCESS',
                    observed_at=finish,bid_timestamp=observed,ask_timestamp=observed,
                    rejection_reasons=[],quality_warnings=[])],
                questionable_contracts=[],rejected_contracts=[]))
        mutate(p)
        raw=gzip.compress(json.dumps(p,sort_keys=True).encode(),mtime=0)
        path=f'options/symbol={symbol}/date=2026-11-03/{stamp:%H%M%S}.json.gz'
        self.objects[path]=raw
        row=dict(id=str(len(self.rows)+1),provider='Public',symbol=symbol,session_date=p['session'],
            slot_time=slot,observed_at=p['observed_at'],created_at=p['collection_finished_at'],
            archive_path=path,archive_sha256=hashlib.sha256(raw).hexdigest(),
            quality_status=p['options']['status'],contract_count=p['options']['received_contract_count'])
        self.rows.append(row)
        return p


def read(store,**kw):
    return read_archive_window(store,'SPY',START,END,expiration=EXPIRY,
        contracts=[CONTRACT],as_of=AS_OF,**kw)


def assert_no_completed_pnl(result):
    """Shared invariant, also exercised against unsafe PR35's legacy result."""
    assert result.get('pnl_dollars') is None
    assert result.get('realized_pnl') is None
    assert result.get('eligible_for_pnl', False) is False


def test_failed_selected_expiration_cannot_support_completed_pnl():
    store=Store()
    store.add()
    def failed(p):
        p['options']['status']='partial'
        p['options']['expiration_failures']=[dict(expiration=EXPIRY,reason='chain_retrieval_failed')]
    store.add('2026-11-03T15:05:00+00:00',mutate=failed)
    original=deepcopy((store.rows,store.objects))
    result=read(store)
    assert_no_completed_pnl(result)
    assert result['coverage']['status']=='incomplete_window'
    assert result['coverage']['selected_expiration']['status']=='partial_expiration_coverage'
    assert 'selected_expiration_failed' in result['slots'][1]['reasons']
    assert result['slots'][1]['sufficient_evidence'] is False
    assert result['slots'][0]['sufficient_evidence'] is True
    assert result['eligible_for_pnl'] is False
    assert not {'pnl','entry_price','exit_price','realized_pnl'} & result.keys()
    assert original==(store.rows,store.objects)
import pytest
from modules import historical_archive_window as window


def populated(symbol='SPY'):
    store=Store();store.add(symbol=symbol);store.add('2026-11-03T15:05:00+00:00',symbol=symbol)
    return store


@pytest.mark.parametrize('symbol',['SPY','QQQ'])
def test_complete_window_is_evidence_only_not_pnl(symbol):
    store=populated(symbol)
    r=read_archive_window(store,symbol,START,END,expiration=EXPIRY,
        contracts=[CONTRACT.replace('SPY',symbol)],as_of=AS_OF)
    assert r['coverage']['status']=='complete_window'
    assert r['coverage']['expected_slot_count']==r['coverage']['verified_slot_count']==2
    assert r['coverage']['missing_slot_count']==r['coverage']['invalid_slot_count']==0
    assert r['coverage']['selected_expiration']['status']=='complete_expiration_coverage'
    assert len(r['slots'][0]['observation']['quotes'])==1
    assert r['lifecycle']['sufficient'] is False and r['eligible_for_pnl'] is False
    assert 'bid_size' not in r['slots'][0]['observation']['quotes'][0]


def test_missing_slot_and_partial_snapshot_are_not_filled_from_older_data():
    store=Store();store.add()
    r=read(store)
    assert r['coverage']['missing_slot_count']==1
    assert r['slots'][1]['status']=='missing_observation'
    store.add('2026-11-03T15:05:00+00:00',mutate=lambda p:p['options'].update(status='partial'))
    r=read(store)
    assert r['coverage']['partial_slot_count']==1
    assert r['coverage']['verified_slot_count']==1
    assert r['slots'][1]['selected_expiration_verified']
    assert not r['slots'][1]['sufficient_evidence']


@pytest.mark.parametrize('defect,reason',[
    ('checksum','checksum_mismatch'),('unavailable','payload_unavailable'),
    ('corrupt','payload_invalid'),('metadata','snapshot_metadata_invalid'),
    ('duplicate','duplicate_observation'),
])
def test_integrity_failures_never_lose_good_observations(defect,reason):
    store=populated();row=store.rows[1]
    if defect=='checksum':row['archive_sha256']='0'*64
    elif defect=='unavailable':del store.objects[row['archive_path']]
    elif defect=='corrupt':
        store.objects[row['archive_path']]=b'corrupt'
        row['archive_sha256']=hashlib.sha256(b'corrupt').hexdigest()
    elif defect=='metadata':row['contract_count']=2
    else:store.rows.append(deepcopy(row))
    r=read(store)
    assert reason in r['slots'][1]['reasons']
    assert r['coverage']['verified_slot_count']==1
    assert r['slots'][0]['sufficient_evidence']
    assert r['coverage']['status']!='complete_window'


@pytest.mark.parametrize('defect,reason',[
    ('failed','selected_expiration_failed'),('not_requested','selected_expiration_missing'),
    ('missing_leg','missing_contract_leg'),('wrong_contract','contract_identity_mismatch'),
    ('rejected','invalid_contract_evidence'),('duplicate_contract','duplicate_contract_evidence'),
    ('stale','stale_quote'),('future','invalid_quote_chronology'),
    ('missing_timestamp','invalid_contract_evidence'),('crossed','invalid_bid_ask_evidence'),
    ('outcome','invalid_bid_ask_evidence'),('order','out_of_order_timestamps'),
])
def test_selected_expiration_and_contract_evidence(defect,reason):
    def mutate(p):
        o=p['options']; row=o['valid_contracts'][0]
        if defect=='failed':
            o['status']='partial';o['expiration_failures']=[dict(expiration=EXPIRY)]
        elif defect=='not_requested':o['requested_expirations']=['2026-11-09']
        elif defect=='missing_leg':o['valid_contracts']=[]
        elif defect=='wrong_contract':row['strike']=601
        elif defect=='rejected':row['rejection_reasons']=['invalid_contract_identifier']
        elif defect=='duplicate_contract':o['valid_contracts'].append(deepcopy(row))
        elif defect=='stale':row['bid_timestamp']='2026-11-03T14:55:00+00:00'
        elif defect=='future':row['ask_timestamp']='2026-11-03T15:05:21+00:00'
        elif defect=='missing_timestamp':row.pop('ask_timestamp')
        elif defect=='crossed':row['bid']=2
        elif defect=='outcome':row['quote_outcome']='UNKNOWN'
        else:o['requests'][0]['started_at']='2026-11-03T15:05:21+00:00'
    store=Store();store.add();store.add('2026-11-03T15:05:00+00:00',mutate=mutate)
    r=read(store)
    assert reason in r['slots'][1]['reasons']
    assert not r['slots'][1]['sufficient_evidence']
    assert r['eligible_for_pnl'] is False


def test_historical_quote_age_does_not_use_read_clock_or_contract_count_change():
    store=Store();store.add()
    store.add('2026-11-03T15:05:00+00:00',mutate=lambda p:p['options'].update(received_contract_count=2540))
    assert read(store)['coverage']['status']=='complete_window'
    assert read_archive_window(store,'SPY',START,END,expiration=EXPIRY,contracts=[CONTRACT],
        as_of='2027-01-01T00:00:00+00:00')['coverage']['status']=='complete_window'


def test_query_failure_unknown_not_a_fabricated_missing_window(monkeypatch):
    store=populated()
    monkeypatch.setattr(store,'execute',lambda:(_ for _ in ()).throw(RuntimeError('PRIVATE SENTINEL')))
    r=read(store)
    assert r['coverage']['status']=='unknown_coverage'
    assert r['coverage']['expected_slot_count']==2
    assert r['coverage']['missing_slot_count'] is None
    assert 'PRIVATE SENTINEL' not in json.dumps(r)


def test_calendar_unavailable_unknown_without_query(monkeypatch):
    monkeypatch.setattr(window,'regular_session_bounds',lambda *a:(_ for _ in ()).throw(RuntimeError('calendar')))
    r=read(Store())
    assert r['coverage']['expected_slot_count'] is None
    assert r['coverage']['status']=='unknown_coverage'
    assert r['coverage']['reasons']==['session_schedule_unavailable']


@pytest.mark.parametrize('start,end,reason',[
    ('2026-11-03T15:01:00+00:00',END,'unaligned_window'),
    ('2026-11-03T14:00:00+00:00',END,'outside_regular_session'),
    (START,'2026-11-04T15:10:00+00:00','outside_regular_session'),
    ('2026-11-01T15:00:00+00:00','2026-11-01T15:10:00+00:00','outside_regular_session'),
])
def test_unsupported_schedules_are_unknown(start,end,reason):
    r=read_archive_window(Store(),'SPY',start,end,expiration=EXPIRY,contracts=[CONTRACT],
        as_of='2026-11-05T00:00:00+00:00')
    assert r['coverage']['status']=='unknown_coverage'
    assert r['coverage']['reasons']==[reason]


@pytest.mark.parametrize('kwargs',[
    dict(symbol='IWM'),dict(contracts=[]),dict(contracts=[CONTRACT,CONTRACT]),
    dict(contracts=['QQQ261106C00600000']),dict(expiration='2026-11-09'),
    dict(max_quote_age_seconds=float('nan')),dict(max_quote_age_seconds=901),
    dict(max_observation_age_seconds=0),dict(as_of=START),dict(start='2026-11-03T15:00:00'),
])
def test_invalid_requests_never_query(kwargs):
    args=dict(symbol='SPY',start=START,end=END,expiration=EXPIRY,contracts=[CONTRACT],as_of=AS_OF)
    args.update(kwargs)
    with pytest.raises(ValueError):read_archive_window(Store(),**args)


def test_unordered_database_response_is_canonicalized_without_overwriting():
    store=populated();store.rows.reverse()
    original=deepcopy((store.rows,store.objects))
    r=read(store)
    assert r['coverage']['status']=='complete_window'
    assert [s['slot_time'] for s in r['slots']]==[START,'2026-11-03T15:05:00+00:00']
    assert original==(store.rows,store.objects)


def test_early_close_schedule_and_exact_close_exclusion():
    r=read_archive_window(Store(),'SPY','2026-11-27T17:50:00+00:00','2026-11-27T18:00:00+00:00',
        expiration='2026-11-27',contracts=['SPY261127C00600000'],as_of='2026-11-27T19:00:00+00:00')
    assert r['coverage']['expected_slot_count']==2
    assert r['coverage']['missing_slot_count']==2
    assert all(s['slot_time']<'2026-11-27T18:00:00+00:00' for s in r['slots'])


@pytest.mark.parametrize('defect',['truncated','count_missing','bad_shape'])
def test_metadata_completeness_must_be_proven(monkeypatch,defect):
    store=populated();execute=store.execute
    def response():
        r=execute()
        if defect=='truncated':r.count+=1
        elif defect=='count_missing':r.count=None
        else:r.data=None
        return r
    monkeypatch.setattr(store,'execute',response)
    r=read(store)
    assert r['coverage']['status']=='unknown_coverage'
    assert r['coverage']['missing_slot_count'] is None


def test_reused_metadata_identity_invalidates_both_observations():
    store=populated();store.rows[1]['id']=store.rows[0]['id']
    r=read(store)
    assert r['coverage']['verified_slot_count']==0
    assert all('duplicate_or_out_of_order_observation' in s['reasons'] for s in r['slots'])


def test_out_of_order_payload_collection_fails_closed():
    store=Store();store.add()
    store.add('2026-11-03T15:05:00+00:00',mutate=lambda p:p.update(collection_finished_at=START))
    assert read(store)['coverage']['invalid_slot_count']==1


def test_stale_snapshot_has_distinct_reason():
    store=Store()
    def delayed(p):
        p['observed_at']='2026-11-03T15:05:10+00:00'
        p['collection_finished_at']='2026-11-03T15:05:20+00:00'
        p['options']['collection_started_at']=p['observed_at']
        p['options']['generated_at']=p['collection_finished_at']
    store.add(mutate=delayed)
    r=read(store,max_observation_age_seconds=60)
    assert r['slots'][0]['status']=='stale_observation'
    assert 'stale_observation' in r['coverage']['reasons']

def test_real_sdk_uses_only_bounded_reads_with_exact_count(monkeypatch):
    import httpx
    from supabase import create_client
    store=populated();calls=[]
    def handle(transport,request):
        calls.append(request)
        assert request.method=='GET'
        if request.url.path=='/rest/v1/option_snapshots':
            assert request.headers['prefer']=='count=exact'
            assert request.url.params['slot_time']=='gte.'+START
            assert request.url.params.get_list('slot_time')==['gte.'+START,'lt.'+END]
            assert request.url.params['limit']=='501'
            return httpx.Response(200,json=store.rows,headers={'content-range':'0-1/2'})
        path=request.url.path.split('/market-archive/')[1]
        return httpx.Response(200,content=store.objects[path])
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',handle)
    sdk=create_client('https://fixture.invalid','fixture-key')
    r=read(sdk)
    assert r['coverage']['status']=='complete_window'
    assert len(calls)==3


def test_no_hidden_pagination_when_service_caps_results(monkeypatch):
    store=populated();execute=store.execute
    def response():
        r=execute();r.data=r.data[:1];return r
    monkeypatch.setattr(store,'execute',response)
    assert read(store)['coverage']['status']=='unknown_coverage'


def test_full_regular_session_expected_slots():
    r=read_archive_window(Store(),'SPY','2026-11-03T14:30:00+00:00','2026-11-03T21:00:00+00:00',
        expiration=EXPIRY,contracts=[CONTRACT],as_of='2026-11-03T22:00:00+00:00')
    assert r['coverage']['expected_slot_count']==r['coverage']['missing_slot_count']==78


def test_all_requested_legs_required_and_no_price_or_size_imputation():
    store=populated()
    r=read_archive_window(store,'SPY',START,END,expiration=EXPIRY,
        contracts=[CONTRACT,'SPY261106P00600000'],as_of=AS_OF)
    assert r['coverage']['verified_slot_count']==0
    assert all('missing_contract_leg' in s['reasons'] for s in r['slots'])
    assert all(s['observation']['quotes']==[] for s in r['slots'])


@pytest.mark.parametrize('field,value,reason',[
    ('session','2026-11-02','snapshot_identity_mismatch'),
    ('observed_at','2026-11-03T14:00:00+00:00','out_of_order_timestamps'),
    ('collection_finished_at','2026-11-03T21:10:00+00:00','out_of_order_timestamps'),
])
def test_snapshot_chronology_and_context(field,value,reason):
    store=Store();store.add();store.add('2026-11-03T15:05:00+00:00',mutate=lambda p:p.update({field:value}))
    r=read(store)
    assert r['coverage']['status']!='complete_window'
    assert r['slots'][1]['status']=='invalid_observation'
    assert reason in r['slots'][1]['reasons']


def test_zero_returned_contracts_does_not_support_complete_evidence():
    store=Store()
    def empty(p):p['options'].update(status='empty',received_contract_count=0,valid_contracts=[])
    store.add(mutate=empty)
    assert read(store)['coverage']['partial_slot_count']==1
