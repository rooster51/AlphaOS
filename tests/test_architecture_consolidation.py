"""Compatibility checks for the small consolidation changes and audit tooling."""
from unittest.mock import Mock
import asyncio
import importlib
import pytest

from tests.test_api_hardening import env, manual
from scripts.inventory_architecture import python_graph, reachable, web_graph


def test_existing_rest_and_mcp_compatibility_surface_is_preserved():
    app = importlib.import_module('alphaos_api.app').app
    expected_paths = {
        '/health', '/v1/market/{symbol}', '/v1/structure/{symbol}', '/v1/distribution/{symbol}',
        '/v1/quote/{symbol}', '/v1/options/{symbol}/expirations', '/v1/options/{symbol}/chain/{expiration}',
        '/v1/options/{symbol}/vertical', '/v1/options/{symbol}/scan', '/v1/candidates/{candidate_id}',
        '/v1/trade/research', '/v1/trade/compare', '/v1/research/{symbol}/run',
        '/v1/research/candidates/{candidate_id}', '/v1/research/{symbol}/vertical', '/v1/research/trade',
        '/v1/research/market', '/v1/research/structure', '/v1/research/structures/compare',
    }
    paths = app.openapi()['paths']
    assert set(paths) == expected_paths
    assert all(operation.get('security') for path, methods in paths.items() if path.startswith('/v1/')
               for operation in methods.values())
    tools = asyncio.run(app.state.mcp.list_tools())
    assert {tool.name for tool in tools} == {
        'market_snapshot','price_structure','forward_distribution','live_quote','option_expirations',
        'scan_credit_spreads','research_candidate','research_vertical','research_explicit_trade','compare_trades',
        'run_symbol_research','unified_candidate_research','unified_vertical_research','unified_explicit_trade_research',
        'run_market','research_structure','compare_structures',
    }
    assert all(tool.annotations.read_only_hint and not tool.annotations.destructive_hint for tool in tools)


@pytest.mark.parametrize('costs', [
    dict(commission_per_contract=0, entry_slippage=0, terminal_friction=0),
    dict(commission_per_contract=1.25, entry_slippage=.10, terminal_friction=.20),
])
def test_compatible_explicit_trade_handlers_preserve_identical_friction(env, monkeypatch, costs):
    client, _, service, _ = env
    research = Mock(wraps=service.research)
    monkeypatch.setattr(service, 'research', research)
    request = dict(manual(), **costs)
    for path in ('/v1/trade/research', '/v1/research/trade'):
        response = client.post(path, json=request)
        assert response.status_code == 200, response.text
    assert research.call_count == 2
    assert all(call.kwargs == costs for call in research.call_args_list)
    assert research.call_args_list[0].args[1:] == research.call_args_list[1].args[1:]


def test_inventory_resolves_relative_lazy_and_test_imports_without_executing_them(tmp_path):
    sources = {
        'alphaos_api/__init__.py': '',
        'alphaos_api/entry.py': 'from . import shared\ndef f():\n from modules.worker import run\n',
        'alphaos_api/shared.py': 'raise AssertionError("Inventory must not import application code")\n',
        'modules/__init__.py': '',
        'modules/worker.py': 'def run(): pass\n',
        'tests/test_one.py': 'from test_two import helper\n',
        'tests/test_two.py': 'def helper(): pass\n',
    }
    for path, text in sources.items():
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    _, edges, _, lazy, _ = python_graph(tmp_path, list(sources))
    assert 'alphaos_api.shared' in edges['alphaos_api.entry']
    assert 'modules.worker' in lazy['alphaos_api.entry']
    assert 'modules.worker' in reachable(edges, ['alphaos_api.entry'])
    assert 'tests.test_two' in edges['tests.test_one']


def test_web_inventory_includes_aliases_reexports_and_dynamic_imports(tmp_path):
    sources = {
        'web/src/app/page.tsx': 'export { default } from "@/components/Main";',
        'web/src/components/Main.tsx': 'const a = import("../lib/shared");',
        'web/src/lib/shared.ts': 'export const value = 1;',
        'web/src/components/Unused.tsx': 'export const Unused = 1;',
    }
    for path, text in sources.items():
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    edges = web_graph(tmp_path, list(sources))
    used = reachable(edges, ['web/src/app/page.tsx'])
    assert 'web/src/components/Main.tsx' in used
    assert 'web/src/lib/shared.ts' in used
    assert 'web/src/components/Unused.tsx' not in used
