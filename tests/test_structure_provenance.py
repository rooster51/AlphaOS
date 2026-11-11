"""Synthetic, explicitly labeled archive fixtures; never live/trade evidence."""
from copy import deepcopy
from decimal import Decimal
import json
import hashlib
from pathlib import Path

import pytest

from tests.test_research2_api import boundary, post, repack as pack_fixture
from tests.test_mcp_api import login, call

EXPIRATIONS = ['2030-01-02','2030-01-04','2030-01-18','2031-01-17']
SHAPES = {
    'long_call': [('Call',500,1)], 'long_put': [('Put',500,1)],
    'call_debit': [('Call',500,1),('Call',505,-1)],
    'put_debit': [('Put',495,-1),('Put',500,1)],
    'put_credit': [('Put',490,1),('Put',495,-1)],
    'call_credit': [('Call',505,-1),('Call',510,1)],
    'call_butterfly': [('Call',495,1),('Call',500,-2),('Call',505,1)],
    'put_butterfly': [('Put',495,1),('Put',500,-2),('Put',505,1)],
    'bullish_bwb': [('Put',490,1),('Put',500,-2),('Put',505,1)],
    'bearish_bwb': [('Call',495,1),('Call',500,-2),('Call',510,1)],
    'iron_condor': [('Put',490,1),('Put',495,-1),('Call',505,-1),('Call',510,1)],
}


def repack(storage):
    pack_fixture(storage)
    # gzip's OS header is not portable across zlib versions/platforms. Pin this
    # fixture header explicitly; real archive checksums remain byte-for-byte.
    raw = bytearray(storage.raw)
    raw[9] = 255
    storage.raw = bytes(raw)
    storage.row['archive_sha256'] = hashlib.sha256(storage.raw).hexdigest()


def prepare(storage, symbol='QQQ', expiry=EXPIRATIONS[0]):
    p = storage.payload
    p['symbol'] = p['options']['symbol'] = symbol
    p['underlying'].update(symbol=symbol, last=500, last_timestamp=p['observed_at'])
    p['options']['requested_expirations'] = [expiry]
    bids = {490:11.,495:6.5,500:3.,505:1.,510:.2}
    rows = []
    for kind in ('Call','Put'):
        for strike in bids:
            bid = bids[strike if kind == 'Call' else 1000-strike]
            rows.append(dict(symbol=symbol, expiration=expiry, type=kind.lower(),
                contract=f'{symbol}{expiry[2:].replace("-","")}{kind[0]}{strike*1000:08}',
                strike=strike,bid=bid,ask=float(Decimal(str(bid))+Decimal('.1')),
                bid_timestamp=p['observed_at'],ask_timestamp=p['observed_at'],observed_at=p['observed_at'],
                rejection_reasons=[],quality_warnings=['Synthetic test observation']))
    p['options'].update(valid_contracts=rows,questionable_contracts=[],rejected_contracts=[])
    storage.row.update(symbol=symbol, archive_path=f'options/symbol={symbol}/date=2030-01-02/fixture.json.gz')
    repack(storage)
    requests = []
    for shape in SHAPES.values():
        legs, credit = [], Decimal(0)
        for kind,strike,qty in shape:
            row = next(r for r in rows if r['type']==kind.lower() and r['strike']==strike)
            legs.append(dict(type=kind,strike=strike,qty=qty,contract=row['contract']))
            credit -= Decimal(str(row['ask'] if qty>0 else row['bid']))*qty
        requests.append(dict(symbol=symbol,expiration=expiry,as_of='2030-01-02',spot=500,
            credit=float(credit),fees=1.25,legs=legs,
            market_data=dict(snapshot_id=storage.row['id'],archive_sha256=storage.row['archive_sha256'])))
    return requests


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
@pytest.mark.parametrize('expiry', EXPIRATIONS)
def test_all_shapes_horizons_rest_mcp_and_hypothetical_economics(boundary,symbol,expiry):
    c,storage,_,_ = boundary
    bodies = prepare(storage,symbol,expiry)
    before = deepcopy(storage.payload)
    for body in bodies:
        response = post(c,'structure',body)
        assert response.status_code == 200, response.text
        data = response.json()['research']
        evidence = data['evidence']['market_data']
        assert evidence['verified'] and not evidence['verified_for_trading']
        assert evidence['snapshot']['archive_sha256'] == storage.row['archive_sha256']
        assert evidence['underlying']['spot'] == 500
        assert evidence['signed_package_cashflow'] == body['credit']
        for original,leg,position in zip(body['legs'], evidence['legs'],data['position']['legs']):
            assert original['contract'] == leg['contract'] == position['contract']
            assert leg['snapshot_id'] == position['snapshot_id'] == storage.row['id']
            assert leg['expiration'] == expiry and leg['qty'] == original['qty']
            assert leg['bid_timestamp'] == position['bid_timestamp'] == storage.payload['observed_at']
            assert leg['ask_timestamp'] == position['ask_timestamp']
            assert leg['freshness']['bid_age_seconds'] == 180
        assert data['payoff']['trade']['legs'] == data['trade']['legs']
        hypothetical = deepcopy(body)
        hypothetical.pop('market_data')
        for leg in hypothetical['legs']: leg.pop('contract')
        manual = post(c,'structure',hypothetical).json()['research']
        assert manual['evidence']['market_data']['kind'] == 'hypothetical'
        assert not manual['evidence']['market_data']['verified']
        for key in ('max_profit','max_loss','capital_at_risk'):
            assert data[key] == manual[key]
        for key in ('breakevens','net_cash','return_on_risk'):
            assert data['payoff'][key] == manual['payoff'][key]
    compare = dict(structures=bodies,thesis='Synthetic parity validation; not a trade')
    response = post(c,'structures/compare',compare)
    assert response.status_code == 200, response.text
    envelope = response.json()
    for researched,projected in zip(envelope['research']['candidates'],envelope['research']['comparison']['candidates']):
        assert projected['market_data'] == researched['evidence']['market_data']
    assert envelope['research']['comparison']['winner'] is None
    assert envelope['research']['comparison']['recommendation'] is None
    _,tokens = login(c)
    result = call(c,tokens['access_token'],'compare_structures',{'comparison':compare})
    assert not result.get('isError'), result
    assert result['structuredContent'] == envelope
    single = call(c,tokens['access_token'],'research_structure',{'structure':bodies[0]})
    assert single['structuredContent'] == post(c,'structure',bodies[0]).json()
    assert storage.payload == before


@pytest.mark.parametrize('defect', ['checksum','reference_checksum','date','rollover','missing_contract','identity','strike','type',
    'expiry','spot','cashflow','duplicate','stale_bid','stale_ask','future','missing_timestamp',
    'crossed','negative','rejected','collection_failed','mixed_underlying','stale_archive','underlying_timestamp'])
def test_integrity_failures_never_downgrade_or_reprice(boundary,defect):
    c,storage,service,loader = boundary
    body = prepare(storage)[2]
    row = storage.payload['options']['valid_contracts'][2]
    # This is the selected bought call at 500.
    assert row['contract'] == body['legs'][0]['contract']
    if defect == 'checksum': storage.row['archive_sha256'] = '0'*64
    elif defect == 'reference_checksum': body['market_data']['archive_sha256'] = '0'*64
    elif defect == 'date': body['as_of'] = '2030-01-01'
    elif defect == 'rollover': body['market_data']['snapshot_id'] = 'previous-snapshot'
    elif defect == 'missing_contract': body['legs'][0]['contract'] = 'QQQ300102C00600000'
    elif defect == 'identity': row['contract'] = body['legs'][0]['contract'] = 'SPY300102C00500000'
    elif defect == 'strike': body['legs'][0]['strike'] = 501
    elif defect == 'type': body['legs'][0]['type'] = 'Put'
    elif defect == 'expiry': body['expiration'] = '2030-01-04'
    elif defect == 'spot': body['spot'] = 501
    elif defect == 'cashflow': body['credit'] += .01
    elif defect == 'duplicate': storage.payload['options']['valid_contracts'].append(deepcopy(row))
    elif defect == 'stale_bid': row['bid_timestamp'] = '2030-01-02T20:00:00Z'
    elif defect == 'stale_ask': row['ask_timestamp'] = '2030-01-02T20:00:00Z'
    elif defect == 'future': row['ask_timestamp'] = '2030-01-03T20:00:00Z'
    elif defect == 'missing_timestamp': row['bid_timestamp'] = None
    elif defect == 'crossed': row['bid'] = row['ask']+1
    elif defect == 'negative': row['bid'] = -1
    elif defect == 'rejected': row['rejection_reasons'] = ['bad_contract']
    elif defect == 'collection_failed': storage.payload['options']['expiration_failures'] = [dict(expiration=body['expiration'])]
    elif defect == 'mixed_underlying': row['symbol'] = 'SPY'
    elif defect == 'stale_archive': service.clock = lambda: __import__('datetime').datetime.fromisoformat('2030-01-02T20:40:00+00:00')
    elif defect == 'underlying_timestamp': storage.payload['underlying']['last_timestamp'] = None
    if defect not in ('checksum','reference_checksum','date','rollover','missing_contract','strike','type','expiry','spot','cashflow','stale_archive'):
        repack(storage)
        body['market_data']['archive_sha256'] = storage.row['archive_sha256']
    response = post(c,'structure',body)
    assert response.status_code in (422,503),response.text
    assert 'research' not in response.json()
    assert 'owner-test-secret' not in response.text
    comparison = post(c,'structures/compare',dict(structures=[prepare_body_without_reference(body),body]))
    assert comparison.status_code in (422,503)
    loader.assert_not_called()


def prepare_body_without_reference(body):
    body = deepcopy(body)
    body.pop('market_data')
    for leg in body['legs']: leg.pop('contract',None)
    return body


def test_comparison_pins_one_read_per_symbol_and_keeps_modes_distinct(boundary):
    c,storage,service,_ = boundary
    bodies = prepare(storage)
    from unittest.mock import Mock
    service.read_snapshot = Mock(wraps=service.read_snapshot)
    request = dict(structures=[bodies[0],prepare_body_without_reference(bodies[1]),bodies[2]])
    result = post(c,'structures/compare',request)
    assert result.status_code == 200
    assert service.read_snapshot.call_count == 1
    assert [x['evidence']['market_data']['kind'] for x in result.json()['research']['candidates']] == [
        'verified_archive','hypothetical','verified_archive']


@pytest.mark.parametrize('mutation', ['no_reference','missing_leg_id','client_bid','client_verified'])
def test_request_cannot_self_certify_quotes(boundary,mutation):
    c,storage,_,_ = boundary
    body = prepare(storage)[2]
    if mutation == 'no_reference': body.pop('market_data')
    elif mutation == 'missing_leg_id': body['legs'][0].pop('contract')
    elif mutation == 'client_bid': body['legs'][0]['bid'] = 3
    else: body['market_data']['verified'] = True
    assert post(c,'structure',body).status_code == 422


def test_committed_website_schema_fixture_matches_actual_rest_and_mcp(boundary):
    from tests.test_archive_read_path import ReadOnlyClient
    from modules.supabase_archive import read_latest_option_snapshot
    fixture = json.loads((Path(__file__).parents[1]/'web/tests/fixtures/structure-provenance-parity.json').read_text())
    c,_,service,_ = boundary
    storage = {s:ReadOnlyClient() for s in ('SPY','QQQ')}
    bodies = {s:prepare(client,s,'2030-01-18') for s,client in storage.items()}
    service.read_snapshot = lambda symbol,as_of:read_latest_option_snapshot(storage[symbol],symbol,as_of,max_age_seconds=300)
    for symbol in bodies:
        assert post(c,'structure',bodies[symbol][2]).json() == fixture['single'][symbol]
    result = post(c,'structures/compare',fixture['comparison']['request'])
    assert result.status_code == 200,result.text
    assert result.json() == fixture['comparison']
    _,tokens = login(c)
    assert call(c,tokens['access_token'],'compare_structures',{'comparison':fixture['comparison']['request']})['structuredContent'] == result.json()
