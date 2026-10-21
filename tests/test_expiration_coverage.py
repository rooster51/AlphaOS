"""Synthetic provider/verified-storage fixtures; no production coverage claims."""
from datetime import datetime
import pytest

from modules.expiration_coverage import classify_expiration, select_expirations, archive_coverage
from modules.intraday_archive import collect_symbol, load_config
from modules.supabase_archive import read_latest_option_snapshot
from tests.test_research2_api import boundary, post, repack
from tests.test_daily_quant import quote
from test_mcp_api import login, call


def test_new_website_fixtures_match_actual_collector_archive_rest_and_mcp(boundary):
    import json
    from pathlib import Path
    from tests.test_website_mcp_parity import expected_fixture
    client, storage, service, _ = boundary
    for case in json.loads((Path(__file__).parents[1]/'web/tests/fixtures/expiration-parity.json').read_text()):
        symbol = case['request']['symbol']
        storage.payload = collect_symbol(Provider(),symbol,load_config())
        storage.row.update(symbol=symbol,quality_status=storage.payload['options']['status'],
            observed_at=storage.payload['observed_at'],slot_time=None,
            archive_path=f'options/symbol={symbol}/date=2030-01-02/fixture.json.gz')
        repack(storage)
        expected = case['response']
        expected['research']['archive']['storage']['archive_sha256'] = storage.row['archive_sha256']
        response=post(client,'market',case['request'])
        assert response.status_code == 200
        assert response.json() == expected_fixture(expected)
        _,tokens=login(client)
        assert call(client,tokens['access_token'],'run_market',case['request'])['structuredContent'] == response.json()


@pytest.mark.parametrize('day,expiry,horizon,kind,valid', [
    ('2030-01-02','2030-01-02','0dte','other_listed_date',True),
    ('2030-01-02','2030-01-03','1dte','other_listed_date',True),
    ('2030-01-02','2030-01-04','weekly','other_listed_date',True),
    ('2030-01-02','2030-01-18','monthly','standard_monthly_date',True),
    ('2030-01-02','2031-01-17','long_dated','standard_monthly_date',True),
    ('2025-04-01','2025-04-17','monthly','standard_monthly_date',True),  # Good Friday
    ('2025-04-01','2025-04-18','other','other_listed_date',False),
    ('2030-01-04','2030-01-07','weekly','other_listed_date',True),  # 3 calendar days
    ('2030-01-02','2030-01-05','weekly','other_listed_date',False),
    ('2030-01-02','2030-01-01','other','other_listed_date',False),
])
def test_calendar_labels_never_synthesize_expirations(day, expiry, horizon, kind, valid):
    result = classify_expiration(day, expiry)
    assert (result['horizon'],result['calendar_kind'],result['eligible_date']) == (horizon,kind,valid)


class Provider:
    name = 'Public'
    expiries = ['2030-01-02','2030-01-03','2030-01-04','2030-01-18','2030-02-15','2031-01-17','2032-01-16']
    def __init__(self): self.calls = []
    def now(self): return datetime.fromisoformat('2030-01-02T20:30:00+00:00')
    def underlying(self, symbol):
        return dict(instrument=dict(symbol=symbol,type='EQUITY'),outcome='SUCCESS',last=100,lastTimestamp=self.now().isoformat())
    def expirations(self, symbol): return self.expiries
    def chain(self, symbol, expiry):
        self.calls.append(expiry)
        rows = []
        for kind in ('C','P'):
            for strike in (80,100,105,120):
                row = quote(symbol,kind,expiration=expiry,strike=strike,
                    bidTimestamp=self.now().isoformat(),askTimestamp=self.now().isoformat(),lastTimestamp=self.now().isoformat())
                rows.append(row)
        return dict(calls=rows[:4],puts=rows[4:])


@pytest.mark.parametrize('symbol',['SPY','QQQ'])
def test_bounded_collector_adds_monthly_and_long_dated_and_keeps_strike_filter(symbol):
    provider = Provider()
    snapshot = collect_symbol(provider, symbol, load_config())
    assert provider.calls == ['2030-01-02','2030-01-03','2030-01-04','2030-01-18','2031-01-17']
    options = snapshot['options']
    assert options['expiration_discovery']['provider_expirations'] == provider.expiries
    assert options['excluded_strike_count'] == 20
    assert options['status'] == 'complete'
    assert all(95 <= row['strike'] <= 105 for row in options['valid_contracts']+options['questionable_contracts'])
    assert set(archive_coverage(options,'2030-01-02')['horizons']) == {'0dte','1dte','weekly','monthly','long_dated'}
    assert all(h['status']=='archived_observations' for h in archive_coverage(options,'2030-01-02')['horizons'].values())


def test_no_discovered_long_dates_means_missing_evidence_not_substitution():
    provider = Provider(); provider.expiries = ['2030-01-02','2030-01-03']
    result = collect_symbol(provider,'SPY',load_config())
    coverage = archive_coverage(result['options'],'2030-01-02')
    assert coverage['horizons']['monthly']['status'] == 'missing_verified_evidence'
    assert coverage['horizons']['long_dated']['expirations'] == []
    assert provider.calls == provider.expiries


def test_extended_selection_rejects_holidays_weekends_malformed_and_past_monthlies():
    dates = ['2029-12-21','2030-01-01','2030-01-05','not-a-date',[], '2030-01-18','2031-01-17']
    selected, audit = select_expirations(dates,'2030-01-02',load_config())
    assert selected == ['2030-01-18','2031-01-17']
    assert audit['invalid_expiration_count'] == 4


def test_archived_weekend_is_unavailable_not_replaced_by_another_expiration():
    from tests.test_market_archive_adapter import payload
    from modules.market_archive_adapter import normalize_archive_snapshot, ArchiveExpirationUnavailable
    source = payload(); source['options']['requested_expirations'].append('2030-01-05')
    with pytest.raises(ArchiveExpirationUnavailable):
        normalize_archive_snapshot(source,'2030-01-05')


@pytest.mark.parametrize('symbol',['SPY','QQQ'])
@pytest.mark.parametrize('expiry',Provider.expiries[:4]+['2031-01-17'])
@pytest.mark.parametrize('mode',['current','historical'])
def test_actual_collector_verified_archive_rest_and_mcp_exact_expiration(boundary,symbol,expiry,mode):
    client, storage, service, _ = boundary
    storage.payload = collect_symbol(Provider(),symbol,load_config())
    storage.row.update(symbol=symbol,quality_status=storage.payload['options']['status'],
        observed_at=storage.payload['observed_at'],slot_time=None,
        archive_path=f'options/symbol={symbol}/date=2030-01-02/fixture.json.gz')
    repack(storage)
    request = dict(symbol=symbol,expiration=expiry,research_mode=mode)
    response = post(client,'market',request)
    assert response.status_code == 200, response.text
    result = response.json()['research']
    assert result['research_mode'] == mode
    assert result['archive']['freshness']['max_age_seconds'] == (None if mode == 'historical' else 300)
    assert result['expiration'] == result['research_session']['expiration'] == expiry
    assert all(candidate['research']['trade']['expiration']==expiry for candidate in result['research_session']['candidates'])
    assert result['archive']['expiration_coverage']['horizons']['long_dated']['expirations'] == ['2031-01-17']
    _, tokens = login(client)
    assert call(client,tokens['access_token'],'run_market',request)['structuredContent'] == response.json()
    absent = post(client,'market',dict(symbol=symbol,expiration='2030-02-15'))
    assert absent.status_code == 422
    assert absent.json()['error']['code'] == 'archive_expiration_unavailable'


def test_failed_long_chain_remains_missing_and_never_promotes_candidates():
    provider = Provider(); original = provider.chain
    def fail(symbol, expiry):
        if expiry == '2031-01-17': raise RuntimeError('fixture provider unavailable')
        return original(symbol,expiry)
    provider.chain = fail
    result = collect_symbol(provider,'QQQ',load_config())
    assert result['options']['status'] == 'partial'
    coverage = archive_coverage(result['options'],'2030-01-02')
    assert coverage['horizons']['long_dated']['status'] == 'missing_verified_evidence'
    assert coverage['horizons']['monthly']['status'] == 'archived_observations'


@pytest.mark.parametrize('symbol',['SPY','QQQ'])
@pytest.mark.parametrize('defect',['stale','checksum'])
def test_explicit_long_date_does_not_bypass_archive_verification(boundary,symbol,defect):
    from unittest.mock import Mock
    client, storage, service, _ = boundary
    if symbol == 'SPY':
        from tests.test_website_mcp_parity import prepare_storage
        prepare_storage(storage,symbol)
    if defect == 'stale':
        service.clock = lambda: datetime.fromisoformat('2030-01-02T21:00:00+00:00')
    else:
        storage.row['archive_sha256'] = 'invalid'
    service.history_loader = Mock(side_effect=AssertionError('No fallback'))
    response = post(client,'market',dict(symbol=symbol,expiration='2031-01-17'))
    assert response.status_code == 503
    assert response.json()['error']['code'] == ('archive_stale' if defect == 'stale' else 'archive_unavailable')
    service.history_loader.assert_not_called()
