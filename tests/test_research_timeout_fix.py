"""Scalar-copy parity and readiness preparation; no live provider operations."""
from copy import deepcopy
from decimal import Decimal
from unittest.mock import Mock
import importlib
import logging

import pytest
from modules.options_payoff import copy_trade_input
from modules.position_research import research_position
from tests.test_structure_research import trade


@pytest.mark.parametrize('side,credit', [('Call',-2),('Put',2)])
def test_quote_copy_preserves_economics_and_independent_mutable_observations(side,credit,monkeypatch):
    candidate=trade([(side,100,1),(side,105,-1)],credit)
    shared={'notes':['retained'], 'decimal':Decimal('.25')}
    for leg in candidate['legs']:
        leg.update(bid=1.,ask=1.1,delta=.3,quality_warnings=shared['notes'],metadata=shared)
    reference=deepcopy(candidate)
    copied=copy_trade_input(candidate)
    assert copied==reference
    assert copied['legs'][0]['metadata'] is copied['legs'][1]['metadata']
    assert copied['legs'][0]['quality_warnings'] is copied['legs'][1]['metadata']['notes']
    assert copied['legs'][0]['metadata'] is not shared
    copied['legs'][0]['metadata']['notes'].append('changed')
    assert candidate==reference
    import modules.structure_research as module
    actual=research_position(candidate,symbol='QQQ',spot=100,as_of='2030-01-17',payoff_detail='none')
    monkeypatch.setattr(module,'copy_trade_input',deepcopy)
    expected=research_position(candidate,symbol='QQQ',spot=100,as_of='2030-01-17',payoff_detail='none')
    assert actual==expected


def test_copy_preserves_self_references_and_custom_deepcopy():
    class Custom:
        def __deepcopy__(self,memo):
            return 'custom-copy'
    candidate={'legs':[{'strike':100,'qty':1,'type':'Call'}], 'custom':Custom()}
    candidate['self']=candidate
    candidate['legs'][0]['owner']=candidate
    candidate['metadata']={'legs':candidate['legs']}
    copied=copy_trade_input(candidate)
    assert copied['self'] is copied
    assert copied['legs'][0]['owner'] is copied
    assert copied['metadata']['legs'] is copied['legs']
    assert copied['custom']=='custom-copy'


def test_subclass_copy_hooks_keep_legacy_behavior():
    class Trade(dict):
        def __deepcopy__(self,memo):return {'hook':'retained'}
    assert copy_trade_input(Trade(legs=[]))=={'hook':'retained'}


def test_runtime_preparation_has_no_archive_or_provider_reads(monkeypatch,caplog):
    runtime=importlib.import_module('alphaos_api.__main__')
    calendar=importlib.import_module('modules.research_calendar')
    archive=importlib.import_module('modules.supabase_archive')
    monkeypatch.setenv('PUBLIC_API_SECRET','fixture-secret')
    monkeypatch.setenv('SUPABASE_URL','https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','fixture-key')
    schedule=Mock()
    monkeypatch.setattr(calendar,'nyse_schedule',schedule)
    transport=Mock()
    monkeypatch.setattr(archive,'research_archive_client',Mock(return_value=transport))
    imported=Mock()
    monkeypatch.setattr(runtime,'import_module',imported)
    with caplog.at_level(logging.WARNING,logger='alphaos_api.runtime'):
        runtime.prepare_research_runtime()
    assert schedule.call_count==3
    assert [call.args[0] for call in imported.call_args_list]==['public_api_sdk','modules.public_history']
    archive.research_archive_client.assert_called_once_with()
    assert not transport.mock_calls
    assert 'fixture-secret' not in caplog.text and 'fixture-key' not in caplog.text


def test_optional_history_and_archive_preparation_failure_keeps_fail_closed_runtime(monkeypatch):
    runtime=importlib.import_module('alphaos_api.__main__')
    monkeypatch.setenv('PUBLIC_API_SECRET','fixture-secret')
    monkeypatch.setenv('SUPABASE_URL','https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','fixture-key')
    monkeypatch.setattr(importlib.import_module('modules.research_calendar'),'nyse_schedule',Mock())
    monkeypatch.setattr(runtime,'import_module',Mock(side_effect=ImportError('private')))
    monkeypatch.setattr(importlib.import_module('modules.supabase_archive'),'research_archive_client',Mock(side_effect=ValueError('private')))
    runtime.prepare_research_runtime()


def test_entrypoint_prepares_runtime_before_starting_server(monkeypatch):
    runtime=importlib.import_module('alphaos_api.__main__')
    monkeypatch.setenv('ALPHAOS_API_TOKEN','fixture-token')
    monkeypatch.setenv('PORT','8000')
    calls=[]
    monkeypatch.setattr(runtime,'prepare_research_runtime',lambda:calls.append('prepare'))
    monkeypatch.setattr(importlib.import_module('uvicorn'),'run',lambda *args,**kwargs:calls.append('serve'))
    runtime.main()
    assert calls==['prepare','serve']

def test_cancellation_during_candidate_copy_cannot_return_partial_economics(monkeypatch):
    import asyncio
    from modules.research_control import cancellable_research
    module=importlib.import_module('modules.structure_research')
    candidate=trade([('Call',100,1),('Call',105,-1)],-2)
    with cancellable_research() as cancelled:
        def copy_and_cancel(value):
            result=copy_trade_input(value)
            cancelled.set()
            return result
        monkeypatch.setattr(module,'copy_trade_input',copy_and_cancel)
        with pytest.raises(asyncio.CancelledError):
            research_position(candidate,symbol='QQQ',spot=100,as_of='2030-01-17',payoff_detail='none')


@pytest.mark.parametrize('legs', [[],[{'type':'Call','qty':1}],[{'type':'Call','strike':100,'qty':0}]])
def test_incomplete_candidates_keep_the_existing_validation_gate(legs):
    candidate=dict(symbol='QQQ',expiration='2030-01-18',spot=100,credit=-2,shares=0,fees=0,legs=legs)
    with pytest.raises(ValueError):
        research_position(candidate,symbol='QQQ',spot=100,as_of='2030-01-17',payoff_detail='none')
