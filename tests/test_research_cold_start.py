"""Cold/warm read-only transport, concurrency, contract and fail-closed tests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event, Lock
from unittest.mock import Mock

import httpx
import pytest

from modules import supabase_archive as archive
from tests.test_archive_read_path import ReadOnlyClient, AS_OF
from tests.test_research2_api import boundary, post
from tests.test_website_mcp_parity import prepare_storage, CASES, expected_fixture
from test_mcp_api import login, call


@pytest.fixture
def transport_boundary(boundary, monkeypatch):
    client, _, service, _ = boundary
    storages = {symbol: ReadOnlyClient() for symbol in ('SPY', 'QQQ')}
    for symbol, storage in storages.items():
        prepare_storage(storage, symbol)
    monkeypatch.setenv('SUPABASE_URL', 'https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'private-fixture-key')
    monkeypatch.setenv('ALPHAOS_ARCHIVE_MAX_AGE_SECONDS', '300')
    monkeypatch.setattr(archive, '_research_client', None)
    monkeypatch.setattr(archive, '_research_credentials', None)
    requests, made = [], []
    lock = Lock()
    def handle(request):
        with lock:
            requests.append(request)
        assert request.method == 'GET'
        assert request.headers['apikey'] == 'private-fixture-key'
        assert request.headers['authorization'] == 'Bearer private-fixture-key'
        if request.url.path == '/rest/v1/option_snapshots':
            if create.metadata_barrier is not None:
                create.metadata_barrier.wait(timeout=5)
            symbol = request.url.params['symbol'].removeprefix('eq.')
            assert dict(request.url.params) == dict(select='*', provider='eq.Public',
                symbol='eq.'+symbol, observed_at='lte.'+AS_OF, created_at='lte.'+AS_OF,
                order='observed_at.desc,id.desc', limit='1')
            assert request.headers['accept-profile'] == 'public'
            return httpx.Response(200, json=[storages[symbol].row] if storages[symbol].row else [])
        for storage in storages.values():
            if request.url.path == '/storage/v1/object/market-archive/'+storage.row['archive_path']:
                return httpx.Response(200, content=storage.raw)
        raise AssertionError('Unexpected archive request')
    def factory(*credentials):
        result = archive.ResearchArchiveHTTP(*credentials, transport=httpx.MockTransport(handle))
        made.append(result)
        return result
    create = Mock(side_effect=factory)
    create.metadata_barrier = None
    monkeypatch.setattr(archive, '_research_archive_transport', create)
    service.read_snapshot = service._read
    yield client, service, storages, requests, create
    for item in made:
        item._http.close()


@pytest.mark.parametrize('mode', ['current', 'historical'])
@pytest.mark.parametrize('symbols', [('SPY',), ('QQQ',), ('SPY', 'QQQ')])
def test_independent_and_concurrent_cold_then_warm_keep_full_contract(transport_boundary, mode, symbols):
    client, service, storages, requests, create = transport_boundary
    # Compare the new wire transport with the original SDK-compatible fixture
    # reader and then exercise both cold and warm real REST handlers.
    service.read_snapshot = lambda symbol, as_of, **kwargs: archive.read_latest_option_snapshot(
        storages[symbol], symbol, as_of, max_age_seconds=300, **kwargs)
    expected = {symbol: post(client, 'market', dict(symbol=symbol, research_mode=mode)).json()
        for symbol in symbols}
    service.read_snapshot = service._read
    def invoke(symbol):
        response = post(client, 'market', dict(symbol=symbol, research_mode=mode))
        assert response.status_code == 200
        assert response.json() == expected[symbol]
        return response.json()
    entered, release = Event(), Event()
    original_factory = create.side_effect
    def blocked_create(*args):
        entered.set()
        assert release.wait(timeout=5)
        return original_factory(*args)
    create.side_effect = blocked_create
    if len(symbols) == 2:
        create.metadata_barrier = Barrier(2)
    try:
        with ThreadPoolExecutor(len(symbols)) as pool:
            futures = [pool.submit(invoke, symbol) for symbol in symbols]
            assert entered.wait(timeout=5)
            assert create.call_count == 1
            release.set()
            for future in futures:
                future.result(timeout=10)
        with ThreadPoolExecutor(len(symbols)) as pool:
            list(pool.map(invoke, symbols))
    finally:
        release.set()
    assert create.call_count == 1
    assert len(requests) == 4*len(symbols)  # query + verified download, every run
    create.metadata_barrier = None
    for symbol in symbols:
        _, tokens = login(client)
        result = call(client, tokens['access_token'], 'run_market', dict(symbol=symbol, research_mode=mode))
        assert not result.get('isError')
        assert result['structuredContent'] == expected[symbol]


@pytest.mark.parametrize('case', CASES, ids=['spy150', 'spy500', 'qqq1dte', 'qqqweekly', 'spyweekly'])
def test_cold_transport_matches_website_fixture_and_oauth_mcp(transport_boundary, case):
    client, _, storages, _, create = transport_boundary
    expected = deepcopy(case['response'])
    expected['research']['archive']['storage']['archive_sha256'] = storages[case['request']['symbol']].row['archive_sha256']
    response = post(client, 'market', case['request'])
    assert response.status_code == 200
    assert response.json() == expected_fixture(expected)
    _, tokens = login(client)
    assert call(client, tokens['access_token'], 'run_market', case['request'])['structuredContent'] == response.json()
    assert create.call_count == 1


@pytest.mark.parametrize('defect,code,downloads', [
    ('checksum', 'archive_unavailable', 1), ('identity', 'archive_unavailable', 1),
    ('stale', 'archive_stale', 0), ('future', 'archive_stale', 0),
    ('path', 'archive_unavailable', 0), ('missing', 'archive_missing', 0)])
def test_cold_and_warm_invalid_evidence_remains_closed(transport_boundary, defect, code, downloads):
    client, service, storages, requests, create = transport_boundary
    storage = storages['QQQ']
    if defect == 'checksum': storage.row['archive_sha256'] = 'invalid'
    elif defect == 'identity':
        from tests.test_research2_api import repack
        storage.payload['provider'] = 'Other'
        repack(storage)
    elif defect == 'stale': storage.row['observed_at'] = '2030-01-02T19:00:00Z'
    elif defect == 'future': storage.row['observed_at'] = '2030-01-03T20:30:00Z'
    elif defect == 'path': storage.row['archive_path'] = 'invalid/path'
    else: storage.row = None
    service.history_loader = Mock(side_effect=AssertionError('No unverified history fallback'))
    for _ in range(2):
        response = post(client, 'market', dict(symbol='QQQ'))
        assert response.status_code == 503
        assert response.json()['error']['code'] == code
    assert create.call_count == 1
    assert len(requests) == 2*(1+downloads)
    service.history_loader.assert_not_called()


@pytest.mark.parametrize('failure', ['http', 'redirect', 'json', 'shape', 'timeout', 'storage'])
def test_transport_failures_are_sanitized_and_never_retried(failure):
    calls = []
    storage = ReadOnlyClient()
    def handle(request):
        calls.append(request)
        if failure == 'timeout': raise httpx.ReadTimeout('private-fixture-key', request=request)
        if failure == 'http': return httpx.Response(503, text='private-fixture-key')
        if failure == 'redirect': return httpx.Response(302, headers={'location':'https://other.invalid/private'})
        if failure == 'json': return httpx.Response(200, text='private-fixture-key')
        if failure == 'shape': return httpx.Response(200, json={'data':[storage.row]})
        if len(calls) == 1: return httpx.Response(200, json=[storage.row])
        return httpx.Response(503, text='private-fixture-key')
    client = archive.ResearchArchiveHTTP('https://fixture.invalid', 'private-fixture-key', transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(archive.ArchiveUnavailable) as error:
            archive.read_latest_option_snapshot(client, 'QQQ', AS_OF, max_age_seconds=300)
        assert 'private' not in str(error.value)
        assert len(calls) == (2 if failure == 'storage' else 1)
    finally:
        client._http.close()


def test_new_transport_matches_actual_sdk_wire_query_and_verified_record():
    from supabase import create_client
    from unittest.mock import patch
    storage = ReadOnlyClient()
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.path == '/rest/v1/option_snapshots':
            return httpx.Response(200, json=[storage.row])
        return httpx.Response(200, content=storage.raw)
    with patch.object(httpx.HTTPTransport, 'handle_request', lambda transport, request: handle(request)):
        sdk = create_client('https://fixture.invalid', 'fixture-key')
        expected = archive.read_latest_option_snapshot(sdk, 'QQQ', AS_OF, max_age_seconds=300)
    client = archive.ResearchArchiveHTTP('https://fixture.invalid', 'fixture-key', transport=httpx.MockTransport(handle))
    try:
        actual = archive.read_latest_option_snapshot(client, 'QQQ', AS_OF, max_age_seconds=300)
        assert actual == expected
        for old, new in zip(requests[:2], requests[2:], strict=True):
            assert old.method == new.method == 'GET'
            assert old.url.path == new.url.path
            assert dict(old.url.params) == dict(new.url.params)
            assert old.headers['authorization'] == new.headers['authorization']
            assert old.headers['apikey'] == new.headers['apikey']
            assert old.extensions['timeout'] == new.extensions['timeout']
    finally:
        client._http.close()


def test_fresh_api_process_does_not_load_sdk_or_fetch_evidence_at_initialization():
    import os
    import subprocess
    import sys
    source = '''
import sys, ssl
from unittest.mock import patch
import alphaos_api.app
from modules.supabase_archive import research_archive_client, ArchiveUnavailable
with patch.dict('os.environ', SUPABASE_URL='https://fixture.invalid', SUPABASE_SERVICE_ROLE_KEY='fixture-key'):
    with patch('httpx.HTTPTransport.handle_request', side_effect=AssertionError('Unexpected initialization I/O')) as network:
        client = research_archive_client()
        assert research_archive_client() is client
        assert 'supabase' not in sys.modules
        assert client._http._transport._pool._ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert client._http._transport._pool._ssl_context.check_hostname
        network.assert_not_called()
        with patch.dict('os.environ', SUPABASE_SERVICE_ROLE_KEY=''):
            try:
                research_archive_client()
            except ArchiveUnavailable as error:
                assert error.code == 'archive_not_configured'
            else:
                raise AssertionError('Reused invalidated credentials')
        client._http.close()
'''
    result = subprocess.run([sys.executable, '-c', source], env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
