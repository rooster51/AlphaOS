# Queued backend: configurable archive universe

## Release status and overlap audit (2026-10-12)

Last recorded shipped main/Render SHA from issue #27: `7f7ef53c85151711ef5fdc3c5d092a7a3e6d84cb` (not reverified against Render here). Release 1 website remains ACTIVE; this is unshipped queued Release 2 preparation. No merge, deployment, collector activation, schema or credential changes. The release-discipline comment prohibits additional feature PRs until release exit/closure; publish this reviewable branch without another feature PR. Website #19/#26/#28 and their files remain untouched.

Base is #33 head `d9b828758f07e066daac6a4b0805c117865e1a6f`. It includes #31 `b2bd429b4c5db919b417e8cf942bb4f65cb222aa` and #32 `e2bb6109c1adc7dcc81956f41251cfe8349c0d41`; #30 `27a9812d61269f0c1fda347f26fd43a5c6fc1178` foundation is already included once. Do not separately reapply these commits.

#35 `2fbbe5e146bb6e4993e5a9f2d6d87ee48c5d1f10` has passing CI 38277529834, but introduces a separate historical evaluator, window reader and an 18th MCP tool. It conflicts with this branch in `modules/supabase_archive.py`: its extracted `_archive_read_policy` must reuse `enabled_archive_symbols` and forward the explicit symbol policy to both latest and window reads during a future reviewed reconciliation. Do not merge it blindly.

Concrete #35 defect reproduced with actual collector-produced fixture bytes through the checksum reader: `normalize_contract` archives lower-case `call`/`put`, while #35 `_quote_row` compares directly to the normalized trade's `Call`/`Put`. Both entry and exit return `contract_identity_mismatch`. Its acceptance of partial snapshots and selection of older eligible records also differ from #33's rejection policy. These semantics require explicit reconciliation; green fixture CI does not establish payload compatibility. This task does not modify #35.

Earlier in-progress broader strategy/archive code is preserved only on local branch `research/verified-archive-multistrategy` at `8547ab6` (137 focused tests passed before checkpoint). It overlaps #35 and is NOT included or published as a competing evaluator. #34 remains separate/deferred.

## Existing data path and gates

Public authenticated SDK -> `public_intraday` candles and `intraday_archive.collect_symbol` -> `options_archive` normalization -> `supabase_archive.persist_*` -> Postgres metadata plus private `market-archive` gzip bytes. Read path: authorized server-side client -> `read_latest_option_snapshot` (symbol/provider/cutoff selection, checksum, path, identity, slot/freshness validation) -> archive adapter/research -> REST/MCP. The #33 evaluator accepts the verified envelope and applies complete-snapshot, identity, bid/ask, quote age, NYSE session, same-contract and timestamp-order checks. No new provider/collector/reader/evaluator is added.

Persistence uses immutable object POST with x-upsert=false, exact-object recovery, metadata uniqueness and duplicate-slot checks. Per-symbol slot/observation and collection completion remain separate. Retries and safe logging are unchanged. Candles, metadata and paths are symbol-keyed; no table is created per ticker.

## Configuration (nothing activated)

- `config/archive_universe.json`: reviewed capability registry, optional NVDA/IWM, maximum two additional symbols per run. It lists capabilities, not enabled collection. Future liquid equity symbols can be reviewed into this registry without ticker-specific implementations; provider entitlement and runtime checks are still required.
- Default collection remains SPY then QQQ.
- Existing `ALPHAOS_INTRADAY_CANARY=NVDA` or `IWM` still enables one extra symbol.
- New `ALPHAOS_INTRADAY_ADDITIONAL_SYMBOLS=NVDA,IWM` explicitly enables both, in supplied order after core symbols. Empty/unset/none disables extras. Duplicates, unknown symbols, core symbols, empty tokens or simultaneous active legacy/new flags fail before authentication.
- Reader opt-in is independent and server-side: `read_latest_option_snapshot(client, symbol, cutoff, max_age_seconds=..., additional_symbols=('NVDA','IWM'))`. Default is still SPY/QQQ. No environment setting silently expands API access.
- Existing REST/MCP Pydantic symbol contracts remain SPY/QQQ. New symbols are therefore unavailable through those interfaces pending reviewed contract wiring and real-data verification. Existing 17 tools and all auth behavior remain unchanged.
- Existing required runtime secrets remain PUBLIC_API_SECRET, PUBLIC_ACCOUNT_NUMBER, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY. No new secrets.

`ArchiveUnavailable.reason` supplies safe categories: archive_missing, archive_stale_or_future, archive_not_yet_available, archive_checksum_mismatch, archive_invalid, archive_unreadable. Disabled/unsupported symbols reject before querying. Latest partial evidence is still returned with its quality_status (never replaced with an older snapshot); the existing evaluator rejects it. Quote freshness is distinct from archive age.

## Evidence and permissions

Read-only production metadata inspection returned 364 complete snapshots each for SPY and QQQ, with 364 matching Storage catalog entries each, most recent observations on October 12 at 17:46 UTC. No NVDA/IWM rows were returned. Catalog existence is NOT byte/checksum or quote validation. Local SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY are absent; connected tools do not expose private-object downloads, so real private payload verification remains blocked.

Inspected repository schema and live pg_policies: authenticated SELECT policies exist for public.market_candles, public.option_snapshots and market-archive Storage objects. Research needs metadata SELECT and private object download/SELECT only. Existing trusted collector uses its server-side service role for writes/verification; never expose it to clients. No policy changes or new migration are needed for symbol expansion. Do not apply market_archive.sql (it contains unrelated journal alterations) or any ledger SQL.

Normal NYSE day: 78 five-minute slots per symbol. Default target is 156 option snapshots/day; one extra is 234; both extras are 312. Early closes/holidays/session gates adjust these counts; failures and scheduler gaps can reduce actual coverage. Two extras approximately double snapshot count, not necessarily byte volume: compressed size depends on contracts and expirations. Each symbol adds existing bars, two underlying quotes, expiration lookup and one chain call per selected expiry, potentially retried once. Confirm quotas, execution time and missed slots before any approved activation; no provider-limit guarantee is claimed.

## Validation and next gate

Focused command: `python -m pytest -q tests/test_configurable_archive_universe.py tests/test_canary_collector_integration.py tests/test_intraday_execution.py tests/test_archive_read_path.py tests/test_canary_intraday_integration.py` — 84 passed in 64.50s. Includes explicit enablement, per-symbol isolation, real constructor reuse, duplicates, conflicting flags, safe failure categories, partial/stale/future/mismatched evidence and actual checksum-reader-to-evaluator fixtures. Full Python 3.12.14 suite results are recorded with the final branch report.

One blocking gate for production claims: authorized private-byte verification with real NVDA/IWM evidence after separately approved activation. Next action is review this queued code and resolve #35's normalization/policy conflict before later REST/MCP expansion. No release has shipped as part of this work.

Final validation: Python 3.12.14 `python -m pytest -q --tb=short` — 825 passed, 40 subtests passed in 347.49 seconds. The full suite includes the existing REST/MCP/authentication, SPY/QQQ, archive/evaluator and canary regressions. `git diff --check` passed. No tests were weakened. No additional feature PR or production verification is claimed.
