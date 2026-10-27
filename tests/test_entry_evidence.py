"""Entry-evidence record: synthetic fixtures only, no archive or provider data."""
from copy import deepcopy
import json
from math import isclose
from pathlib import Path
import ast

import pytest

from modules.entry_evidence import (EVIDENCE_VERSION, MULTIPLIER, VERSION,
    EntryEvidenceError, build_entry_record)
from modules.premium_engine import payoff


def trade():
    return dict(symbol='QQQ', expiration='2030-01-02', spot=500.0, credit=-1.90,
        fees=1.30, shares=0, legs=[
            dict(type='Call', strike=500.0, qty=1, contract='QQQ300102C00500000'),
            dict(type='Call', strike=505.0, qty=-1, contract='QQQ300102C00505000')])


def leg(index, **changes):
    quote = dict(type='Call', strike=500.0, qty=1, symbol='QQQ',
        expiration='2030-01-02', contract='QQQ300102C00500000',
        bid=4.90, ask=5.10, bid_timestamp='2030-01-02T20:24:00+00:00',
        ask_timestamp='2030-01-02T20:24:10+00:00',
        observation_timestamp='2030-01-02T20:25:00+00:00',
        archive_quality='valid_contracts', quality_warnings=[],
        entry_side='ask', entry_price=5.10, snapshot_id='snap-1',
        freshness=dict(evaluated_at='2030-01-02T20:30:00+00:00',
            max_age_seconds=900, bid_age_seconds=360.0, ask_age_seconds=350.0))
    if index:
        quote.update(dict(strike=505.0, qty=-1, contract='QQQ300102C00505000',
            bid=3.20, ask=3.40, entry_side='bid', entry_price=3.20))
    quote.update(changes)
    return quote


def evidence(**changes):
    value = dict(version=EVIDENCE_VERSION, kind='verified_archive', verified=True,
        verified_for_trading=False,
        snapshot=dict(id='snap-1', provider='Public', symbol='QQQ',
            observed_at='2030-01-02T20:25:00+00:00', session_date='2030-01-02',
            archive_path='options/symbol=QQQ/date=2030-01-02/20250102202500.json.gz',
            archive_sha256='a' * 64, quality_status='complete',
            slot_time='2030-01-02T20:25:00+00:00',
            created_at='2030-01-02T20:29:30+00:00'),
        archive_freshness=dict(as_of='2030-01-02T20:30:00+00:00', age_seconds=300.0,
            max_age_seconds=7200.0, basis='collection_start'),
        evaluated_at='2030-01-02T20:30:00+00:00',
        underlying=dict(spot=500.0, timestamp='2030-01-02T20:29:00+00:00'),
        pricing='natural_bid_ask', signed_package_cashflow=-1.90, fees=1.30,
        legs=[leg(0), leg(1)], caveats=['synthetic fixture'])
    value.update(changes)
    return value


def build(ev=None, tr=None):
    return build_entry_record(tr or trade(), ev or evidence())


# ---------------------------------------------------------------- happy path

def test_record_echoes_the_verified_entry_unchanged():
    tr = trade()
    record = build(tr=tr)
    assert record['version'] == VERSION
    assert record['record_type'] == 'entry'
    assert record['symbol'] == 'QQQ' and record['expiration'] == '2030-01-02'
    assert record['multiplier'] == MULTIPLIER and record['shares'] == 0
    assert record['spot'] == 500.0
    assert record['pricing'] == 'natural_bid_ask'
    assert isclose(record['signed_package_cashflow'], -1.90, abs_tol=1e-12)
    assert record['fees'] == 1.30
    assert [row['contract'] for row in record['legs']] == [
        'QQQ300102C00500000', 'QQQ300102C00505000']
    assert [row['entry_side'] for row in record['legs']] == ['ask', 'bid']
    assert [row['entry_price'] for row in record['legs']] == [5.10, 3.20]
    assert record['snapshot']['archive_sha256'] == 'a' * 64
    assert record['verification']['archive_age_seconds'] == 300.0


def test_record_is_research_only_and_never_trade_ready():
    record = build()
    assert record['research_only'] is True
    assert record['verified_for_trading'] is False
    # Entry only: nothing that implies an outcome or a forecast may appear.
    assert not {'exit', 'settlement', 'outcome', 'probability', 'expected_value',
                'ranking'} & set(record)
    assert record['caveats'][1].startswith('Entry evidence only')


def test_record_is_deterministic_and_json_safe():
    first = json.dumps(build(), sort_keys=True)
    second = json.dumps(build(), sort_keys=True)
    assert first == second
    assert json.loads(first) == json.loads(second)
    assert len(build()['fingerprint']) == 64


def test_fingerprint_changes_with_the_evidence_not_the_dict_order():
    reordered = evidence()
    reordered['snapshot'] = dict(reversed(list(reordered['snapshot'].items())))
    assert build(ev=reordered)['fingerprint'] == build()['fingerprint']
    changed = evidence(archive_freshness=dict(as_of='2030-01-02T20:30:00+00:00',
        age_seconds=301.0, max_age_seconds=7200.0, basis='collection_start'))
    assert build(ev=changed)['fingerprint'] != build()['fingerprint']


def test_inputs_are_not_mutated():
    tr, ev = trade(), evidence()
    tr_before, ev_before = deepcopy(tr), deepcopy(ev)
    build(ev=ev, tr=tr)
    assert tr == tr_before and ev == ev_before


def test_existing_payoff_engine_still_owns_the_economics():
    """The record must reproduce the exact trade the payoff engine already prices."""
    tr = trade()
    record = build(tr=tr)
    assert record['signed_package_cashflow'] == tr['credit']
    assert record['fees'] == tr['fees']
    assert [(row['type'], row['strike'], row['qty']) for row in record['legs']] == \
        [(row['type'], row['strike'], row['qty']) for row in tr['legs']]
    expected = payoff(tr['legs'], tr['credit'], 502.5, fees=tr['fees'])
    assert expected == payoff(record['legs'], record['signed_package_cashflow'], 502.5,
        fees=record['fees'])


def test_put_credit_structure_is_supported():
    tr = dict(symbol='SPY', expiration='2030-01-02', spot=600.0, credit=1.25,
        fees=1.30, shares=0, legs=[
            dict(type='Put', strike=590.0, qty=-1, contract='SPY300102P00590000'),
            dict(type='Put', strike=585.0, qty=1, contract='SPY300102P00585000')])
    ev = evidence(signed_package_cashflow=1.25, underlying=dict(spot=600.0,
        timestamp='2030-01-02T20:29:00+00:00'))
    ev['snapshot'].update(symbol='SPY')
    ev['legs'] = [
        leg(0, type='Put', strike=590.0, qty=-1, contract='SPY300102P00590000',
            symbol='SPY', entry_side='bid', entry_price=4.10, bid=4.10, ask=4.30),
        leg(1, type='Put', strike=585.0, qty=1, contract='SPY300102P00585000',
            symbol='SPY', entry_side='ask', entry_price=2.85, bid=2.65, ask=2.85)]
    record = build_entry_record(tr, ev)
    assert record['legs'][0]['entry_side'] == 'bid'
    assert record['legs'][1]['entry_side'] == 'ask'
    assert isclose(record['signed_package_cashflow'], 1.25, abs_tol=1e-12)


# ---------------------------------------------------------------- rejections

@pytest.mark.parametrize('change, code', [
    (dict(kind='hypothetical'), 'entry_evidence_not_verified'),
    (dict(verified=False), 'entry_evidence_not_verified'),
    (dict(version='structure-market-data-v0'), 'entry_evidence_not_verified'),
    (dict(verified_for_trading=True), 'entry_trade_ready_claim'),
    (dict(pricing='midpoint'), 'entry_pricing_unsupported'),
    (dict(evaluated_at=None), 'entry_timestamp_invalid'),
    (dict(evaluated_at='2030-01-02T20:30:00'), 'entry_timestamp_invalid'),
])
def test_evidence_envelope_rejections(change, code):
    with pytest.raises(EntryEvidenceError) as error:
        build(ev=evidence(**change))
    assert error.value.code == code


@pytest.mark.parametrize('field, value, code', [
    ('id', None, 'entry_snapshot_incomplete'),
    ('archive_sha256', 'not-a-checksum', 'entry_snapshot_mismatch'),
    ('archive_sha256', 'A' * 64, 'entry_snapshot_mismatch'),
    ('symbol', 'SPY', 'entry_snapshot_mismatch'),
    ('observed_at', '2030-01-02T20:26:00', 'entry_timestamp_invalid'),
    ('created_at', '2030-01-02T20:24:00+00:00', 'entry_timestamp_invalid'),
    ('slot_time', '2030-01-02T20:26:00+00:00', 'entry_timestamp_invalid'),
    ('session_date', '2030-01-03', 'entry_snapshot_mismatch'),
])
def test_snapshot_rejections(field, value, code):
    ev = evidence()
    ev['snapshot'][field] = value
    with pytest.raises(EntryEvidenceError) as error:
        build(ev=ev)
    assert error.value.code == code


@pytest.mark.parametrize('field, value, code', [
    ('spot', 500.02, 'entry_spot_mismatch'),
    ('spot', 0, 'entry_spot_mismatch'),
    ('timestamp', '2030-01-02T19:00:00+00:00', 'entry_quote_stale'),
    ('timestamp', '2030-01-02T20:31:00+00:00', 'entry_timestamp_invalid'),
])
def test_underlying_rejections(field, value, code):
    ev = evidence()
    ev['underlying'][field] = value
    with pytest.raises(EntryEvidenceError) as error:
        build(ev=ev)
    assert error.value.code == code


@pytest.mark.parametrize('mutation, code', [
    (lambda rows: rows[0].update(contract=None), 'entry_contract_missing'),
    (lambda rows: rows[0].update(contract='QQQ30010C00500000'), 'entry_contract_invalid'),
    (lambda rows: rows[0].update(contract='SPY300102C00500000'), 'entry_contract_mismatch'),
    (lambda rows: rows[0].update(contract='QQQ300102P00500000'), 'entry_contract_mismatch'),
    (lambda rows: rows[0].update(contract='QQQ300102C00501000'), 'entry_contract_mismatch'),
    (lambda rows: rows[1].update(contract='QQQ300102C00500000'), 'entry_contract_duplicate'),
    (lambda rows: rows[0].update(snapshot_id='snap-2'), 'entry_snapshot_mismatch'),
    (lambda rows: rows[0].update(expiration='2030-01-03'), 'entry_contract_mismatch'),
    (lambda rows: rows[0].update(strike=501.0), 'entry_contract_mismatch'),
    (lambda rows: rows[0].update(qty=2), 'entry_leg_mismatch'),
    (lambda rows: rows[0].update(bid=5.20), 'entry_quote_invalid'),
    (lambda rows: rows[0].update(ask=0), 'entry_quote_invalid'),
    (lambda rows: rows[0].update(bid=None), 'entry_quote_invalid'),
    (lambda rows: rows[0].update(bid_timestamp=None), 'entry_quote_invalid'),
    (lambda rows: rows[0].update(bid_timestamp='2030-01-02T19:00:00+00:00'), 'entry_quote_stale'),
    (lambda rows: rows[0].update(freshness=dict(max_age_seconds=900,
        bid_age_seconds=1.0, ask_age_seconds=350.0)), 'entry_quote_invalid'),
    (lambda rows: rows[0].update(archive_quality='rejected_contracts'), 'entry_contract_invalid'),
    (lambda rows: rows[0].update(entry_side='bid'), 'entry_quote_invalid'),
    (lambda rows: rows[0].update(entry_price=5.00), 'entry_quote_invalid'),
])
def test_leg_rejections(mutation, code):
    ev = evidence()
    mutation(ev['legs'])
    with pytest.raises(EntryEvidenceError) as error:
        build(ev=ev)
    assert error.value.code == code


@pytest.mark.parametrize('legs, code', [
    ([], 'entry_leg_count_mismatch'),
    ([leg(0)], 'entry_leg_count_mismatch'),
    ([leg(0), leg(1), leg(0)], 'entry_leg_count_mismatch'),
])
def test_leg_count_rejections(legs, code):
    ev = evidence(legs=legs)
    with pytest.raises(EntryEvidenceError) as error:
        build(ev=ev)
    assert error.value.code == code


@pytest.mark.parametrize('change, code', [
    (dict(signed_package_cashflow=-1.91), 'entry_cashflow_mismatch'),
    (dict(fees=1.31), 'entry_fees_invalid'),
])
def test_cashflow_and_fee_rejections(change, code):
    with pytest.raises(EntryEvidenceError) as error:
        build(ev=evidence(**change))
    assert error.value.code == code


@pytest.mark.parametrize('change, code', [
    (dict(credit=-1.91), 'entry_cashflow_mismatch'),
    (dict(fees=-1), 'entry_fees_invalid'),
    (dict(shares=100), 'entry_shares_unsupported'),
    (dict(multiplier=10), 'entry_multiplier_unsupported'),
    (dict(spot=499.0), 'entry_spot_mismatch'),
    (dict(expiration='2030-01-03'), 'entry_contract_mismatch'),
    (dict(symbol='SPY'), 'entry_snapshot_mismatch'),
    (dict(legs=[]), 'entry_leg_count_mismatch'),
])
def test_trade_rejections(change, code):
    tr = dict(trade(), **change)
    with pytest.raises(EntryEvidenceError) as error:
        build(tr=tr)
    assert error.value.code == code


def test_mixed_snapshots_are_rejected():
    ev = evidence()
    ev['legs'][1]['snapshot_id'] = 'snap-2'
    with pytest.raises(EntryEvidenceError) as error:
        build(ev=ev)
    assert error.value.code == 'entry_snapshot_mismatch'


def test_missing_verified_payload_is_rejected():
    with pytest.raises(EntryEvidenceError) as error:
        build_entry_record(trade(), {})
    assert error.value.code == 'entry_evidence_not_verified'


# ------------------------------------------------------------------ purity

ALLOWED_IMPORTS = {'datetime', 'decimal', 'hashlib', 'json', 'math', 're', 'zoneinfo'}


def test_module_imports_no_io_capable_dependency():
    source = Path(__import__('modules.entry_evidence', fromlist=['x']).__file__).read_text()
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or '').split('.')[0])
    assert roots <= ALLOWED_IMPORTS, sorted(roots - ALLOWED_IMPORTS)
    assert 'open(' not in source
    assert 'requests' not in source and 'httpx' not in source and 'supabase' not in source


def test_evaluated_at_is_the_only_reference_instant():
    """No local clock: moving the evidence instant forward must change ages, not behaviour."""
    record = build()
    assert record['verification']['evaluated_at'] == '2030-01-02T20:30:00+00:00'
    assert isclose(record['verification']['underlying_age_seconds'], 60.0, abs_tol=1e-9)
    assert isclose(record['legs'][0]['bid_age_seconds'], 360.0, abs_tol=1e-9)


def test_verified_evidence_version_matches_the_verifier_when_available():
    provenance = pytest.importorskip('modules.structure_provenance')
    assert provenance.VERSION == EVIDENCE_VERSION
