"""End-to-end evidence integration: synthetic archive -> verifier -> entry record.

Fixtures are built in this file and are explicitly synthetic. No Supabase query,
provider request or real archive object is used, and nothing is persisted.

The chain under test is exactly the production one:

    read_latest_option_snapshot(...)  ->  record{payload, metadata, freshness}
    resolve_structure(request, record, now)  ->  (selected legs, evidence)
    build_entry_record(trade, evidence)      ->  entry record

The first step is replaced by a hand-built record with the same shape; the two
functions under test run unmodified.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from alphaos_api.research2 import StructureLeg, StructureRequest
from modules.entry_evidence import EntryEvidenceError, build_entry_record
from modules.premium_engine import payoff
from modules.structure_provenance import (ProvenanceError, hypothetical_evidence,
    resolve_structure)

NOW = datetime(2026, 10, 21, 20, 31, tzinfo=timezone.utc)
SESSION = '2026-10-21'
EXPIRATION = '2026-10-23'
SHA = 'b' * 64


def contract(root, expiration, side, strike):
    year, month, day = expiration.split('-')
    return f'{root}{year[2:]}{month}{day}{side}{int(round(strike * 1000)):08d}'


def row(kind, strike, bid, ask, contract_symbol, expiration=EXPIRATION,
        bid_timestamp='2026-10-21T20:20:00+00:00',
        ask_timestamp='2026-10-21T20:20:10+00:00'):
    return dict(contract=contract_symbol, type=kind, strike=strike,
        expiration=expiration, symbol=contract_symbol[:3], bid=bid, ask=ask,
        bid_timestamp=bid_timestamp, ask_timestamp=ask_timestamp,
        observed_at='2026-10-21T20:25:00+00:00',
        rejection_reasons=[], quality_warnings=[])


def archive(rows, *, symbol='QQQ', spot=500.0, session=SESSION,
            expiration=EXPIRATION, observed='2026-10-21T20:25:00+00:00',
            finished='2026-10-21T20:25:20+00:00', created='2026-10-21T20:25:30+00:00',
            underlying_timestamp='2026-10-21T20:24:00+00:00',
            snapshot_id='snap-int-1', sha=SHA):
    payload = {
        'schema_version': 'intraday-archive-v1', 'provider': 'Public',
        'symbol': symbol, 'session': session, 'observed_at': observed,
        'slot_time': observed, 'collection_finished_at': finished,
        'underlying': dict(symbol=symbol, last=spot, last_timestamp=underlying_timestamp),
        'options': {
            'schema_version': 'options-archive-v1', 'symbol': symbol, 'provider': 'Public',
            'snapshot_date': session, 'status': 'complete',
            'quote_timing': 'last_available_not_guaranteed_close',
            'collection_started_at': observed, 'generated_at': finished,
            'requested_expirations': [expiration], 'expiration_failures': [],
            'warnings': [], 'requests': [], 'provenance': {},
            'valid_contracts': rows, 'questionable_contracts': [], 'rejected_contracts': [],
        },
    }
    metadata = dict(id=snapshot_id, provider='Public', symbol=symbol, observed_at=observed,
        session_date=session,
        archive_path=f'options/symbol={symbol}/date={session}/snap.json.gz',
        archive_sha256=sha, quality_status='complete', slot_time=observed, created_at=created)
    return dict(payload=payload, metadata=metadata,
        freshness=dict(as_of=NOW.isoformat(), age_seconds=360.0,
            max_age_seconds=600.0, basis='collection_start'))


def request(legs, *, symbol='QQQ', spot=500.0, credit=-1.90, fees=1.30,
            expiration=EXPIRATION, session=date(2026, 10, 21), snapshot_id='snap-int-1',
            sha=SHA):
    # The real request model carries a date, not the wire string.
    expiration = date.fromisoformat(expiration) if isinstance(expiration, str) else expiration
    return SimpleNamespace(symbol=symbol, expiration=expiration, as_of=session,
        spot=spot, credit=credit, fees=fees,
        market_data=SimpleNamespace(snapshot_id=snapshot_id, archive_sha256=sha),
        legs=[SimpleNamespace(**leg) for leg in legs])


def qqq_debit():
    return [dict(type='Call', strike=500.0, qty=1, contract=contract('QQQ', EXPIRATION, 'C', 500)),
            dict(type='Call', strike=505.0, qty=-1, contract=contract('QQQ', EXPIRATION, 'C', 505))]


def qqq_rows(expiration=EXPIRATION):
    return [row('call', 500.0, 4.90, 5.10, contract('QQQ', expiration, 'C', 500), expiration),
            row('call', 505.0, 3.20, 3.40, contract('QQQ', expiration, 'C', 505), expiration)]


def spy_credit():
    return [dict(type='Put', strike=590.0, qty=-1, contract=contract('SPY', EXPIRATION, 'P', 590)),
            dict(type='Put', strike=585.0, qty=1, contract=contract('SPY', EXPIRATION, 'P', 585))]


def spy_rows():
    return [row('put', 590.0, 4.10, 4.30, contract('SPY', EXPIRATION, 'P', 590)),
            row('put', 585.0, 2.65, 2.85, contract('SPY', EXPIRATION, 'P', 585))]


def end_to_end(req, rec):
    selected, evidence = resolve_structure(req, rec, NOW)
    trade = dict(symbol=req.symbol, expiration=req.expiration.isoformat(), spot=req.spot,
        credit=evidence['signed_package_cashflow'], fees=req.fees, shares=0,
        legs=[dict(type=leg['type'], strike=leg['strike'], qty=leg['qty'],
            contract=leg['contract']) for leg in selected])
    return selected, evidence, build_entry_record(trade, evidence), trade


# --------------------------------------------------------------- happy paths

def test_qqq_call_debit_end_to_end():
    selected, evidence, entry, trade = end_to_end(request(qqq_debit()), archive(qqq_rows()))
    assert evidence['kind'] == 'verified_archive' and evidence['verified'] is True
    assert evidence['verified_for_trading'] is False
    assert [leg['contract'] for leg in entry['legs']] == [leg['contract'] for leg in qqq_debit()] \
        == [leg['contract'] for leg in selected]
    assert [leg['strike'] for leg in entry['legs']] == [500.0, 505.0]
    assert [leg['type'] for leg in entry['legs']] == ['Call', 'Call']
    assert [leg['qty'] for leg in entry['legs']] == [1, -1]
    assert [leg['expiration'] for leg in entry['legs']] == [EXPIRATION, EXPIRATION]
    # Quotes are preserved, never recalculated or mid-priced.
    assert [leg['bid'] for leg in entry['legs']] == [4.90, 3.20]
    assert [leg['ask'] for leg in entry['legs']] == [5.10, 3.40]
    assert [leg['entry_side'] for leg in entry['legs']] == ['ask', 'bid']
    assert [leg['entry_price'] for leg in entry['legs']] == [5.10, 3.20]
    assert entry['signed_package_cashflow'] == pytest.approx(-1.90, abs=1e-12)
    assert entry['pricing'] == 'natural_bid_ask'
    assert entry['record_type'] == 'entry' and entry['research_only'] is True
    assert entry['verified_for_trading'] is False


def test_qqq_timestamps_and_snapshot_identity_are_preserved():
    _, evidence, entry, _ = end_to_end(request(qqq_debit()), archive(qqq_rows()))
    assert entry['snapshot']['id'] == evidence['snapshot']['id'] == 'snap-int-1'
    assert entry['snapshot']['archive_sha256'] == SHA
    assert {leg['snapshot_id'] for leg in entry['legs']} == {'snap-int-1'}
    assert {leg['snapshot_id'] for leg in evidence['legs']} == {'snap-int-1'}
    assert entry['legs'][0]['bid_timestamp'] == evidence['legs'][0]['bid_timestamp']
    assert entry['legs'][0]['ask_timestamp'] == evidence['legs'][0]['ask_timestamp']
    assert entry['verification']['evaluated_at'] == evidence['evaluated_at']


def test_spy_put_credit_end_to_end():
    req = request(spy_credit(), symbol='SPY', spot=600.0, credit=1.25)
    _, _, entry, _ = end_to_end(req, archive(spy_rows(), symbol='SPY', spot=600.0))
    assert [leg['entry_side'] for leg in entry['legs']] == ['bid', 'ask']
    assert [leg['entry_price'] for leg in entry['legs']] == [4.10, 2.85]
    assert entry['signed_package_cashflow'] == pytest.approx(1.25, abs=1e-12)


def test_four_leg_iron_condor_end_to_end():
    legs = [
        dict(type='Put', strike=490.0, qty=1, contract=contract('QQQ', EXPIRATION, 'P', 490)),
        dict(type='Put', strike=495.0, qty=-1, contract=contract('QQQ', EXPIRATION, 'P', 495)),
        dict(type='Call', strike=505.0, qty=-1, contract=contract('QQQ', EXPIRATION, 'C', 505)),
        dict(type='Call', strike=510.0, qty=1, contract=contract('QQQ', EXPIRATION, 'C', 510)),
    ]
    rows = [row('put', 490.0, 0.80, 0.95, contract('QQQ', EXPIRATION, 'P', 490)),
        row('put', 495.0, 1.55, 1.70, contract('QQQ', EXPIRATION, 'P', 495)),
        row('call', 505.0, 3.20, 3.40, contract('QQQ', EXPIRATION, 'C', 505)),
        row('call', 510.0, 1.75, 1.90, contract('QQQ', EXPIRATION, 'C', 510))]
    credit = -0.95 + 1.55 + 3.20 - 1.90
    _, _, entry, trade = end_to_end(request(legs, credit=credit), archive(rows))
    assert len(entry['legs']) == 4
    assert len({leg['contract'] for leg in entry['legs']}) == 4
    assert {leg['snapshot_id'] for leg in entry['legs']} == {'snap-int-1'}
    assert entry['signed_package_cashflow'] == pytest.approx(credit, abs=1e-12)
    assert [leg['entry_side'] for leg in entry['legs']] == ['ask', 'bid', 'bid', 'ask']


def test_zero_dte_and_monthly_dates_flow_through_unchanged():
    for expiration in ('2026-10-21', '2026-11-20'):
        rows = qqq_rows(expiration)
        legs = qqq_debit()
        for leg, strike in zip(legs, (500.0, 505.0)):
            leg['contract'] = contract('QQQ', expiration, 'C', strike)
        _, _, entry, _ = end_to_end(
            request(legs, expiration=expiration), archive(rows, expiration=expiration))
        assert entry['expiration'] == expiration
        assert [leg['expiration'] for leg in entry['legs']] == [expiration, expiration]
        assert entry['session_date'] == SESSION


def test_payoff_engine_owns_the_economics_across_the_seam():
    _, _, entry, trade = end_to_end(request(qqq_debit()), archive(qqq_rows()))
    for spot in (480.0, 500.0, 502.5, 505.0, 530.0):
        assert payoff(entry['legs'], entry['signed_package_cashflow'], spot,
            fees=entry['fees']) == payoff(trade['legs'], trade['credit'], spot,
            fees=trade['fees'])


def test_entry_record_is_deterministic_across_repeated_runs():
    first = end_to_end(request(qqq_debit()), archive(qqq_rows()))[2]
    second = end_to_end(request(qqq_debit()), archive(qqq_rows()))[2]
    assert first == second
    assert first['fingerprint'] == second['fingerprint']


def test_inputs_are_not_mutated_by_the_seam():
    req, rec = request(qqq_debit()), archive(qqq_rows())
    req_before, rec_before = deepcopy(req), deepcopy(rec)
    end_to_end(req, rec)
    assert rec == rec_before
    assert [leg.contract for leg in req.legs] == [leg.contract for leg in req_before.legs]


# ------------------------------------------------------- verifier rejections

def test_snapshot_reference_mismatch_is_refused():
    req = request(qqq_debit(), sha='c' * 64)
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(req, archive(qqq_rows()), NOW)
    assert error.value.code == 'archive_snapshot_mismatch'


def test_snapshot_id_mismatch_is_refused():
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit(), snapshot_id='other'), archive(qqq_rows()), NOW)
    assert error.value.code == 'archive_snapshot_mismatch'


def test_wrong_session_date_is_refused():
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit(), session=date(2026, 10, 20)),
            archive(qqq_rows()), NOW)
    assert error.value.code == 'market_data_date_mismatch'


def test_stale_quote_is_refused():
    rows = qqq_rows()
    rows[0]['bid_timestamp'] = '2026-10-21T19:00:00+00:00'
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit()), archive(rows), NOW)
    assert error.value.code == 'market_quote_stale'


def test_future_dated_quote_is_refused():
    # The archive adapter already drops contract rows whose timestamps post-date
    # collection completion, so the contract is unavailable before quote-age
    # validation runs. Either rejection refuses the package; the surfaced code
    # here is the contract one, not the stale-quote one.
    rows = qqq_rows()
    rows[0]['ask_timestamp'] = '2026-10-21T20:40:00+00:00'
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit()), archive(rows), NOW)
    assert error.value.code == 'market_contract_mismatch'


def test_missing_quote_timestamp_is_refused():
    rows = qqq_rows()
    rows[0]['bid_timestamp'] = None
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit()), archive(rows), NOW)
    assert error.value.code == 'market_quote_invalid'


def test_crossed_and_zero_ask_quotes_are_refused():
    for bid, ask in ((5.20, 5.10), (4.90, 0)):
        rows = qqq_rows()
        rows[0].update(bid=bid, ask=ask)
        with pytest.raises(ProvenanceError) as error:
            resolve_structure(request(qqq_debit()), archive(rows), NOW)
        assert error.value.code == 'market_quote_invalid'


def test_invalid_contract_identifier_is_refused():
    legs = qqq_debit()
    legs[0]['contract'] = 'QQQ261023X00500000'
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(legs), archive(qqq_rows()), NOW)
    assert error.value.code == 'market_contract_mismatch'


def test_absent_contract_is_refused():
    legs = qqq_debit()
    legs[0]['contract'] = contract('QQQ', EXPIRATION, 'C', 501)
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(legs), archive(qqq_rows()), NOW)
    assert error.value.code == 'market_contract_mismatch'


def test_cashflow_mismatch_is_refused():
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit(), credit=-1.50), archive(qqq_rows()), NOW)
    assert error.value.code == 'market_data_cashflow_mismatch'


def test_spot_mismatch_is_refused():
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit(), spot=501.0), archive(qqq_rows()), NOW)
    assert error.value.code == 'market_data_spot_mismatch'


def test_rejected_archive_row_cannot_be_selected():
    rec = archive(qqq_rows())
    rec['payload']['options']['valid_contracts'] = rec['payload']['options']['valid_contracts'][1:]
    rec['payload']['options']['rejected_contracts'] = [qqq_rows()[0]]
    with pytest.raises(ProvenanceError) as error:
        resolve_structure(request(qqq_debit()), rec, NOW)
    assert error.value.code == 'market_contract_mismatch'


# --------------------------------------------------- trust-boundary attempts

def test_hypothetical_evidence_cannot_become_an_entry_record():
    _, evidence = resolve_structure(request(qqq_debit()), archive(qqq_rows()), NOW)
    trade = dict(symbol='QQQ', expiration=EXPIRATION, spot=500.0, credit=-1.90,
        fees=1.30, shares=0, legs=qqq_debit())
    with pytest.raises(EntryEvidenceError) as error:
        build_entry_record(trade, hypothetical_evidence())
    assert error.value.code == 'entry_evidence_not_verified'
    assert evidence['kind'] == 'verified_archive'


def test_trade_ready_claim_is_refused():
    _, evidence, _, trade = end_to_end(request(qqq_debit()), archive(qqq_rows()))
    tampered = deepcopy(evidence)
    tampered['verified_for_trading'] = True
    with pytest.raises(EntryEvidenceError) as error:
        build_entry_record(trade, tampered)
    assert error.value.code == 'entry_trade_ready_claim'


def test_client_cannot_supply_quote_fields():
    with pytest.raises(ValidationError):
        StructureLeg(type='Call', strike=500.0, qty=1, contract='QQQ261023C00500000', bid=5.10)
    with pytest.raises(ValidationError):
        StructureLeg(type='Call', strike=500.0, qty=1, contract='QQQ261023C00500000', verified=True)


def test_client_contract_requires_archive_reference():
    with pytest.raises(ValidationError):
        StructureRequest(symbol='QQQ', expiration=EXPIRATION, as_of='2026-10-21', spot=500.0,
            credit=-1.90, legs=[dict(type='Call', strike=500.0, qty=1,
                contract='QQQ261023C00500000')])


def test_archive_reference_requires_every_contract():
    with pytest.raises(ValidationError):
        StructureRequest(symbol='QQQ', expiration=EXPIRATION, as_of='2026-10-21', spot=500.0,
            credit=-1.90, market_data=dict(snapshot_id='snap-int-1', archive_sha256=SHA),
            legs=[dict(type='Call', strike=500.0, qty=1, contract='QQQ261023C00500000'),
                dict(type='Call', strike=505.0, qty=-1)])


def test_entry_builder_is_not_reachable_from_the_http_or_mcp_surface():
    import alphaos_api.research2 as research2
    import alphaos_api.mcp_server as mcp_server
    for module in (research2, mcp_server):
        source = open(module.__file__).read()
        assert 'entry_evidence' not in source
        assert 'build_entry_record' not in source
