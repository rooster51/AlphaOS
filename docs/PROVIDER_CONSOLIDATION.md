# Release 1.5B provider consolidation

Base: `18655f055a7667706f639c83bfb4ef3de75b7d99` (main after PR #45),
October 16, 2026. This is a source/import/call-path review; the prior Render audit
in [DEPLOYMENT.md](DEPLOYMENT.md) is not a new deployment verification.

## Traced active paths

| Observation / consumer | Actual path and retained boundary |
|---|---|
| Live underlying | REST `/v1/quote`, market/context and legacy vertical workflows -> `ResearchService` -> `MarketProvider.quote` -> `public_provider.get_public_quotes`. SDK timestamps and retrieval time remain distinct; service freshness is reevaluated on cache hits. |
| Live options | REST options/vertical/scan and unified legacy research -> `ResearchService` -> `MarketProvider.expirations/chain` -> `public_provider` SDK requests -> `_option_quote_row` -> **shared `public_option_quote.option_quote_row`**. Existing index symbol/response validation remains in the headless provider. |
| Legacy UI options | Streamlit workspace/selector -> `public_data.get_public_option_chain` -> SDK request using the UI context -> `_option_quote_row` -> **same formatter**. UI decorators, `.clear`, instrument mapping and response-symbol behavior remain unchanged. |
| Legacy underlying | `public_data._cached_public_quotes` already delegates to the headless quote loader with UI context; `get_public_quotes` reevaluates freshness after its cache. No new consolidation needed. |
| Daily history | Headless research and UI use `public_history.fetch_research_bars`, with their own context/error/cache wrappers. `ArchiveResearchService._history` uses `public_provider` completed daily history. History failures retain explicit unavailable-evidence diagnostics. |
| Archive collection | `scripts.run_intraday_snapshot` -> session/duplicate gate -> `DailyPublicProvider` -> raw authenticated market-data POSTs -> `intraday_archive.collect_symbol/normalize_underlying_quote` + `options_archive.build_options_snapshot/normalize_contract` -> `supabase_archive.persist_option_snapshot`. Collector retains per-contract malformed observations and quality reasons; candle writes use `persist_candles`. |
| Archive general research | Website `/market` or `/strategies` -> POST `/api/research/market` -> authenticated POST `/v1/research/market` -> `ArchiveResearchService.run` -> verified `read_latest_option_snapshot` -> `run_latest_market` -> `market_archive_adapter.normalize_archive_snapshot` -> existing classification, construction, economics, capital and diagnostics. **The SDK formatter is not inserted into archive research.** |
| MCP | `mcp_server.invoke` uses in-process ASGI authenticated REST. `run_market` uses the archive endpoint; retained live/legacy tools reach the same `ResearchService` as REST. OAuth/owner/read-only metadata remain. |
| Explicit structures | `/v1/research/structure` and compare tools use explicit signed input and the existing payoff/history architecture, not live-chain substitution. |
| Dashboard | `getMarketSnapshotServer` pairs `/v1/market` and `/v1/structure`; separate from archive candidates. Explicit demo mode remains labeled and separate. |

## One consolidation

`public_data._option_quote_row` and `public_provider._option_quote_row` previously
contained the same field transformation, including midpoint fallback. Both now
call `modules/public_option_quote.py`. That module imports only `typing`, has no
SDK/Streamlit/provider imports, and performs no requests, caching, credential
loading, timestamp interpretation or quality validation.

Both old function names/signatures remain. Each wrapper supplies its existing
`_as_float` hook, preserving conversion behavior and module-level overrides. The
formatter returns a fresh row, retains the supplied side label, converts the same
fields, prefers provider midpoint and derives `(bid + ask) / 2` only when midpoint
is absent and both sides exist. Missing option details/strike still return `None`;
malformed numeric values still raise. Missing optional Greeks, timestamps and open
interest remain `None`. Provider timestamps remain unmodified observations.

Formatting is not acceptance: crossed/negative/nonfinite observations are not
silently repaired or dropped here. Existing service/strategy/archive quality gates
still own rejection. No candidate, price, probability, classification or ranking
is introduced, and neither archive/current nor historical semantics change.

## Duplicates intentionally retained

| Boundary | Why it remains separate |
|---|---|
| Credentials/account/context | Headless environment precedence + sanitized `PublicProviderError` + bounded `lru_cache`; UI `st.secrets` + `cache_resource`; collector fresh context and fixed `ProviderUnavailable`. Merging changes failure/lifecycle contracts. |
| Symbol/instrument mapping | Headless registry/index response checks include XSP; legacy UI has a different index set and mapping. Shared-looking helpers resolve different module globals. |
| Request handling | SDK live chains may fail whole-response parsing; collector raw dictionaries retain malformed-contract evidence. They cannot be substituted without losing evidence or changing failures. |
| Cache policy | UI quotes/chains 30s, expirations/history 300s; headless `ResearchService` quote/chain 30s, expirations/history 300s plus snapshot/scan lifetimes; auth caches differ. No cache is moved or added. |
| Underlying/option normalization | Raw archive provenance, numeric/OSI validation, quality and checksums differ from SDK formatting. Archive adapter checks verified context and explicit expiration; `public_observations` remains a test-referenced alternate adapter. |
| History wrappers | Transport already shared, but index mapping, pre-auth validation, error codes and UI caching differ. |
| Fallbacks | Optional history failure yields unavailable evidence; invalid archives never fall back to live or older complete snapshots. Demo context remains explicit. No new provider retry or substitution. |

Next recommended migration: characterize history-wrapper request/error contracts
and symbol policies (ETF and index cases) with deterministic fake clients, then
extract only common history request preparation. Preserve UI cache/secret wrappers
and headless typed error translation. Do not merge client/auth caches or replace
raw archive collection with SDK models as part of that migration.

## Validation

New focused tests cover both retained wrappers, SPY/QQQ golden rows, input
immutability, missing fields, midpoint behavior, malformed-number propagation,
local conversion hooks, request/account forwarding and unchanged transport failure
without retry. Existing index mapping, REST/MCP compatibility, archive integrity,
current/historical freshness, quote quality, economics and website/browser tests
remain intact. Test fixtures are not provider evidence or production candidates.

Final validation on Windows, Python 3.12.14 (existing development environment):

| Check | Exact outcome |
|---|---|
| `python -m pytest -q --tb=short --basetemp=../provider-full-temp` with repository/tests on `PYTHONPATH` | **874 passed, 64 subtests passed in 270.41s** |
| `python -m pytest tests/test_public_option_quote.py -q --tb=short --basetemp=../provider-focused-corrected-temp` | **30 passed in 1.36s** |
| `npm run typecheck` | Passed (exit 0) |
| `npm test` | **61 passed, 0 failed, 0 skipped** |
| `npm run build` | Passed; production routes generated |
| `npm run test:e2e -- --workers=2` | **15 passed in 7.8s** |
| Baseline formatter AST comparison | Both original bodies match the shared body after conversion-hook renaming |
| `git diff --cached --check` | Passed |

An initial focused run reported two failures in a new test's conversion-call
count assertion (expected 11, actual 10); the assertion was corrected. No runtime
behavior was changed to satisfy it. The final focused and full suites passed.
Existing Node module-type and React 18 deprecation warnings remain; dependencies
and tooling configuration were not changed.

No live secret, Render setting, dependency or collector configuration was changed.
