"""Fixture teardown must restore shared API services across pytest versions.

Starlette State routes attributes through its backing dictionary. pytest 9.2's
setattr undo records __dict__ instead, deleting dynamic attributes at teardown.
Patch the actual dictionary so later REST/MCP tests retain the original service.
"""
import importlib
import inspect

import pytest


@pytest.mark.parametrize('module,fixture_name,key', [
    ('tests.test_api_hardening', 'env', 'service'),
    ('tests.test_mcp_api', 'env', 'service'),
    ('tests.test_research2_api', 'boundary', 'archive_research'),
])
def test_api_fixture_restores_state_after_repeated_use(module, fixture_name, key):
    module = importlib.import_module(module)
    state = module.api.app.state
    original = state._state.copy()
    fixture = getattr(module, fixture_name).__wrapped__
    for _ in range(2):
        with pytest.MonkeyPatch.context() as patch:
            result = fixture(patch)
            if inspect.isgenerator(result):
                try:
                    next(result)
                    assert getattr(state, key) is not original[key]
                finally:
                    result.close()
            else:
                assert getattr(state, key) is not original[key]
        assert state._state.keys() == original.keys()
        assert all(getattr(state, name) is value for name, value in original.items())
