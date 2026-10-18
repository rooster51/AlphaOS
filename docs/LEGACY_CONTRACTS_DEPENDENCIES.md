# Release 1.5C legacy contracts and dependency cleanup

Base: main after PR #46, `74eabb42f3226b1fbb354991040b60ed9bede49d`.
This is a source/runtime-metadata review, not a new Render audit or deployment.
Read alongside [ARCHITECTURE.md](ARCHITECTURE.md),
[DEPLOYMENT.md](DEPLOYMENT.md), [provider consolidation](PROVIDER_CONSOLIDATION.md)
and [the regenerated import inventory](architecture-inventory.json).

## Contract inventory and compatibility decisions

All **19 REST operations** (18 authenticated `/v1` operations plus public health)
and **17 OAuth MCP tools** remain. Full local OpenAPI and MCP declarations were
captured before editing and compared after cleanup: identical, including input
schemas, defaults, operation IDs, descriptions, response declarations, security
and read-only annotations. This comparison made no provider requests. Protocol,
OAuth and discovery routes are additional to OpenAPI and remain unchanged.

| Contract family | REST operations | MCP tools / consumers |
|---|---|---|
| Context | GET `/v1/market/{symbol}`, `/v1/structure/{symbol}`, `/v1/distribution/{symbol}`, `/v1/quote/{symbol}` | `market_snapshot`, `price_structure`, `forward_distribution`, `live_quote`. Website dashboard pairs market/structure by snapshot ID. |
| Options/live vertical | GET `/v1/options/{symbol}/expirations`, `/chain/{expiration}`, `/vertical`, `/scan`; GET `/v1/candidates/{candidate_id}` | `option_expirations`, `research_vertical`, `scan_credit_spreads`, `research_candidate`. Saved candidate IDs must not silently reprice. Chain has no separate MCP tool. |
| Explicit legacy vertical | POST `/v1/trade/research`, `/v1/trade/compare` | `research_explicit_trade`, `compare_trades`; `TradeRequest`, `CompareRequest`, `ResearchResponse`, existing friction/context rules. |
| Unified legacy presentation | GET `/v1/research/{symbol}/run`, `/v1/research/candidates/{candidate_id}`, `/v1/research/{symbol}/vertical`; POST `/v1/research/trade` | `run_symbol_research`, `unified_candidate_research`, `unified_vertical_research`, `unified_explicit_trade_research`; `SymbolResearchResponse`, `UnifiedTradeResponse`. This is an active presentation contract, not another engine. |
| Archive/general research | POST `/v1/research/market` | `run_market`; website `/market` and `/strategies` -> POST `/api/research/market`. `MarketRequest`, explicit current/historical modes, `alphaos-interface-v2` envelope. |
| Explicit supported structures | POST `/v1/research/structure`, `/v1/research/structures/compare` | `research_structure`, `compare_structures`; signed explicit input, existing deterministic payoff/history logic. |
| Public process health | GET `/health` | No MCP tool; process health does not certify market evidence. |

Legacy tools are compatibility interfaces with active imports, tests and possible
external consumers. They are not scheduled for removal in this change. Different
horizons, explicit-input conventions, schemas, defaults and freshness policies
prevent simply aliasing all legacy calls to `run_market`.

## Small cleanup implemented

Both explicit legacy vertical handlers duplicated the same sequence:
`manual_trade` validation -> `snapshot(symbol, horizon, explicit spot)` ->
`research(method, commission_per_contract, entry_slippage, terminal_friction)`.
They now call `ResearchService.research_explicit_trade`, which returns the same
bundle, trade and result. No validation, request model, cache, provider or economics
logic moved or changed; validation still precedes all history/provider access.

`/v1/trade/research` retains its `meta/evidence/caveats` envelope.
`/v1/research/trade` retains the five-section unified response and
`include_advanced` option. MCP continues to invoke these authenticated REST
handlers in process and returns their sanitized content. The existing imported
`friction` names in `app` and `phase9_routes` remain available for compatibility.
Explicit spot/credit remain user scenarios; this workflow fetches completed
history without retrieving live underlying quotes or option chains.

The comparison workflow retains its separate shared-context validation and
input ordering. Live exact-trade and saved-candidate paths retain mandatory quote
freshness and their own provenance; they are not folded into the explicit-input
helper. Archive reads/checksums, collector writes, current freshness, explicit
historical mode, candidate construction, capital eligibility and diagnostics are
untouched.

## Dependency and wrapper inventory

| Boundary | Actual imports/ownership and decision |
|---|---|
| `requirements-api.txt` | FastAPI/Uvicorn entrypoint; pandas/NumPy/dateutil research; Public SDK/calendar/tzdata; MCP 2.2.0 and Supabase. Keep the headless install scope. |
| `requirements.txt` | Legacy Streamlit/Plotly UI plus shared research/provider packages. CI installs this with API requirements to test both interfaces. Not redundant with the API scope. |
| `requirements-daily.txt` | Intraday archive and manually dispatched legacy daily workflow; NumPy/pandas, pinned Public SDK/calendar and Supabase 2.32.0. Keep the collector scope. |
| Overlapping declarations | Public SDK 0.1.17 and calendar 5.4.0 are identical pins; NumPy/pandas/Supabase/dateutil bounds differ by scope. No manifest is made to include another, because that would add UI/API packages or alter resolver bounds for a different runtime. |
| Undeclared direct imports | API models use `pydantic`; HTTP/OAuth uses `starlette`, `httpx`, `mcp_types`. These real application imports are currently installed through declared packages. `requests` is required internally by the Public SDK; no direct tracked Python import was found. The older deployment inventory incorrectly grouped it with direct application imports; that description is corrected. |
| Installed dependency evidence | In the tested existing environment: FastAPI 0.141.1 -> Starlette/Pydantic; Public SDK 0.1.17 -> requests/httpx/Pydantic; MCP 2.2.0 -> mcp-types 2.2.0/Pydantic/Starlette; Supabase 2.31.0 -> httpx. These installed versions are evidence, not new constraints or claims about a fresh deployment. |
| Collector isolation limit | The existing test environment has Supabase 2.31.0, whereas the collector manifest pins 2.32.0. Fake-client archive tests do not certify a fresh isolated collector install. No package was installed, removed or upgraded here. |
| Python/Node boundaries | Python 3.12.14 used for tests; CI uses `.python-version`; historical devcontainer 3.11 differs. Website uses package-lock with Node 22 in CI; existing React 18 deprecation, module-type warnings, legacy lint command and reviewed audit exceptions remain. |
| Provider wrappers | 1.5B shared SDK row formatting; UI secret/cache wrappers, headless errors/index mapping and raw collector normalization remain required. `public_observations` is a test-referenced alternate adapter; no external retirement evidence. |
| Website wrappers | `/strategies` reexports the market page. `/api/strategies` POST delegates to the canonical bridge; GET preserves legacy query conversion. Existing browser tests cover those compatibility URLs. |
| Other legacy roots | Both Streamlit launchers and automatic `pages/` discovery remain. Disabled pages and no-incoming-import Python modules stay retained; static absence of imports does not establish external safety. |

The inventory's lazy import closure can reach UI modules from shared files; this
does not mean the headless request path executes those imports. Nothing here
justifies adding Streamlit to the API or deleting a UI dependency. No dependency
manifests, lockfiles, credentials, collector configuration or Render settings
were changed.

## Release 1.5D migration boundary

1. Build separate clean API, UI and collector install environments from existing
   manifests; run import/startup and fake-provider/storage smoke checks in each.
   Record resolution and `pip check`, especially the collector Supabase pin.
2. Add explicit direct dependency declarations using versions/ranges proven in
   each isolated environment; test OAuth/MCP runtime compatibility before changing
   constraints. Consider common constraints only after proving all three scopes;
   do not combine their package lists wholesale.
3. Characterize history-wrapper symbol/error/cache differences (the next provider
   migration identified in 1.5B). Extract only proven common request preparation.
4. Any legacy REST/MCP retirement needs external consumer evidence, a published
   compatibility/deprecation plan and separate authorization. No removals are
   proposed by this inventory.
5. React/toolchain, devcontainer/runtime alignment and staging Blueprint drift
   remain separate migrations, not incidental cleanup in a contract PR.

## Validation

New tests exercise both retained explicit-trade endpoints and MCP tools, both
historical selection methods, nonzero costs and advanced presentation; compare
full REST/MCP responses; reject invalid orientation, credit, expiry, horizon,
symbol and model fields before provider access; and verify sanitized history
failures without live-chain fallback. Existing full-suite checks retain the
19-operation/17-tool surface, OAuth/authentication, archive integrity/freshness,
economics, diagnostics and website compatibility.

Final validation, existing Windows development environment, Python 3.12.14:

| Command / check | Outcome |
|---|---|
| `python -m pytest -q --tb=short --basetemp=../legacy-contract-full-temp` with repository/tests on `PYTHONPATH` | **892 passed, 64 subtests passed in 447.44s** |
| `python -m pytest tests/test_legacy_explicit_contracts.py tests/test_architecture_consolidation.py -q --tb=short --basetemp=../legacy-contract-focused-temp` | **23 passed in 25.32s** |
| `npm run typecheck` | Passed |
| `npm test` | **61 passed, 0 failed, 0 skipped** |
| `npm run build` | Passed; production routes generated |
| `npm run test:e2e -- --workers=2` | **15 passed in 8.0s** |
| Full OpenAPI + all MCP declarations compared to pre-edit baseline | Identical |
| Inventory regenerated against staged tracked files | Exact match; 19 REST operations / 17 tools |
| `git diff --cached --check` | Passed |

No tests were weakened or skipped. Existing Node module-type and React 18
warnings remain. These results cover the development environment and fake-provider
regressions; they do not certify isolated production/collector dependency installs.
No merge, deployment, branch deletion, secret or Render configuration change was
performed.
