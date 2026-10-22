"""Completed responses must not retain source graphs until cyclic GC runs."""
import gc
import weakref

import pytest

from alphaos_api.app import sanitized


@pytest.mark.parametrize('schema',['alphaos-interface-v2','legacy'])
def test_completed_sanitization_releases_source_arrays_without_cyclic_gc(schema,monkeypatch):
    class Observations(list):
        pass
    monkeypatch.setenv('ALPHAOS_API_TOKEN','owner-lifetime-secret')
    enabled=gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        references=[]
        for _ in range(12):
            source=Observations([dict(spot=500.25,note='owner-lifetime-secret')])
            references.append(weakref.ref(source))
            output=sanitized(dict(schema_version=schema,positions=source,evidence=source))
            assert source[0]['note']=='owner-lifetime-secret'
            del source
            assert output['positions']==[dict(spot=500.25,note='[REDACTED]')]
            assert output['evidence']==output['positions']
        assert all(reference() is None for reference in references)
    finally:
        if enabled:gc.enable()
        gc.collect()
