"""Real authenticated REST projection over fixture archives; no hosted claims."""
from copy import deepcopy
import json
import pytest

from alphaos_api.research_projection import candidate_summary, candidate_digest, summarize
from alphaos_api.contracts import APIError
from tests.test_research2_api import boundary, post
from tests.test_website_mcp_parity import prepare_storage


@pytest.mark.parametrize('symbol', ['QQQ', 'SPY'])
@pytest.mark.parametrize('mode', ['current', 'historical'])
@pytest.mark.parametrize('explicit', [False, True])
def test_summary_keeps_all_candidates_counts_order_risk_and_provenance(boundary, symbol, mode, explicit):
    client, storage, _, _ = boundary
    prepare_storage(storage, symbol)
    request = dict(symbol=symbol, available_capital=150, research_mode=mode)
    if explicit:
        request['expiration'] = '2030-01-02'
    full = post(client, 'market', request).json()
    response = post(client, 'market', dict(request, response_format='summary-v1'))
    assert response.status_code == 200, response.text
    summary = response.json()
    old = full['research']['research_session']
    new = summary['research']['research_session']
    assert summary['research']['archive'] == full['research']['archive']
    for bucket in ('candidates', 'excluded'):
        assert len(new[bucket]) == len(old[bucket])
        for index, (before, after) in enumerate(zip(old[bucket], new[bucket])):
            assert before.get('input_index') == after.get('input_index')
            assert after['detail']['index'] == index
            assert after['detail']['bucket'] == bucket
            assert after['detail']['candidate_sha256'] == candidate_digest(before)
            if bucket == 'candidates':
                assert {k:v for k,v in after.items() if k != 'detail'} == candidate_summary(before)
                for key in ('max_loss', 'max_profit', 'capital_at_risk', 'breakevens', 'evidence'):
                    assert after['research'].get(key) == before['research'].get(key)
                assert after['research']['capital_at_risk'] <= 150
            else:
                assert after.get('reason') == before.get('reason')
    assert new['candidate_order'] == old['candidate_order']
    assert new['diagnostics'] == old['diagnostics']
    assert new['transport']['complete'] is True
    assert len(response.content) < len(json.dumps(full).encode())


def test_authenticated_detail_recomputes_exact_candidate_and_fails_on_changes(boundary):
    client, _, _, _ = boundary
    request = dict(symbol='QQQ', available_capital=150)
    full = post(client, 'market', request).json()
    summary = post(client, 'market', dict(request, response_format='summary-v1')).json()
    session = summary['research']['research_session']
    for bucket in ('candidates', 'excluded'):
        for row in session[bucket]:
            ref = row['detail']
            response = post(client, 'market/candidate', dict(request, detail=ref))
            assert response.status_code == 200, response.text
            detail = response.json()
            assert detail['verified_for_trading'] is False
            assert detail['candidate'] == full['research']['research_session'][bucket][ref['index']]
            assert detail['archive'] == full['research']['archive']
            for field in ('candidate_sha256', 'archive_sha256'):
                bad = dict(ref, **{field: '0' * 64})
                assert post(client, 'market/candidate', dict(request, detail=bad)).status_code == 409
    ref = next(row['detail'] for bucket in ('candidates','excluded') for row in session[bucket])
    assert client.post('/v1/research/market/candidate', json=dict(request, detail=ref)).status_code == 401


def test_summary_never_silently_truncates_oversize_response(boundary, monkeypatch):
    client, _, _, _ = boundary
    full = post(client, 'market', dict(symbol='QQQ')).json()
    original = deepcopy(full)
    monkeypatch.setattr('alphaos_api.research_projection.MAX_SUMMARY_BYTES', 1)
    with pytest.raises(APIError) as error:
        summarize(full)
    assert error.value.code == 'research_summary_too_large'
    assert full == original


def test_missing_history_cannot_promote_summary_candidates(boundary):
    client, _, service, _ = boundary
    service.history_loader = lambda symbol: None
    full = post(client, 'market', dict(symbol='QQQ', available_capital=150)).json()
    summary = post(client, 'market', dict(symbol='QQQ', available_capital=150, response_format='summary-v1')).json()
    old, new = (data['research']['research_session'] for data in (full, summary))
    assert new['opportunity_state'] == old['opportunity_state']
    assert new['status'] == old['status']
    assert [row.get('classification_supported') for row in new['candidates']] == [row.get('classification_supported') for row in old['candidates']]


def test_projection_cancellation_is_request_local_and_does_not_mutate_results(boundary, monkeypatch):
    import asyncio
    from modules.research_control import cancellable_research
    import alphaos_api.research_projection as projection
    client, _, _, _ = boundary
    full = post(client, 'market', dict(symbol='QQQ', available_capital=150)).json()
    before = deepcopy(full)
    original = projection.candidate_digest
    with cancellable_research() as cancelled:
        def digest(entry):
            cancelled.set()
            return original(entry)
        monkeypatch.setattr(projection, 'candidate_digest', digest)
        with pytest.raises(asyncio.CancelledError):
            summarize(full)
    monkeypatch.setattr(projection, 'candidate_digest', original)
    assert summarize(full)['research']['research_session']['transport']['complete'] is True
    assert full == before


def test_detail_digests_preserve_unlimited_profit_and_order_independence():
    assert candidate_digest({'a': float('inf')}) != candidate_digest({'a': None})
    assert candidate_digest({'a': 1, 'b': 2}) == candidate_digest({'b': 2, 'a': 1})


@pytest.mark.parametrize('defect', ['missing', 'stale', 'corrupt'])
def test_summary_and_detail_keep_archive_fail_closed(boundary, defect):
    client, storage, service, _ = boundary
    request = dict(symbol='QQQ', available_capital=150)
    summary = post(client, 'market', dict(request, response_format='summary-v1')).json()
    ref = next(row['detail'] for bucket in ('candidates','excluded')
        for row in summary['research']['research_session'][bucket])
    if defect == 'missing':
        storage.row = None
    elif defect == 'corrupt':
        storage.raw = b'corrupt'
    else:
        from datetime import datetime, timedelta
        service.clock = lambda: datetime.fromisoformat('2030-01-02T20:33:00+00:00') + timedelta(hours=1)
    for path, body in [('market', dict(request, response_format='summary-v1')),
                       ('market/candidate', dict(request, detail=ref))]:
        response = post(client, path, body)
        assert response.status_code == 503
        assert 'research' not in response.json()
