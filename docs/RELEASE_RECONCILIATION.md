# Production release reconciliation

Release branch: `release/reconcile-quote-freshness-economics`.
Baseline main: `b39495808d51474ee5f35f13cc8575347f858653` (PRs #20-24 merged).
Deployment baseline supplied by owner: `cd59c2c4026a9505ecd25e1976da241b2dc4c534`.
This is repository reconciliation, not independent verification of Render state.
The final immutable release SHA is recorded in the integration PR.

## Exact reconciliation

The deployed commit `cd59c2c` added the freshness/latency protections. Its older
Phase 7/8 ancestry is divergent from current main and must not be merged wholesale.
Comparison found these already present and retained without changes:

- `modules/quote_freshness.py`, `modules/quote_latency.py`, `scripts/quote_latency.py`.
- API quote cache-age revalidation, contextual/live gates and freshness metadata.
- Public provider timestamp normalization, observation/retrieval distinction.
- Latency allowlisted diagnostics, safe failures and quote/MCP regression tests.
- OAuth consent/PKCE/CIMD, protocol diagnostics, auth configuration and restart revocation.
  OAuth/config/cache files are byte-identical to the deployed baseline.

Restored deployed protections missing from main:

- `modules/market_data.py`: remove historical-close/different-symbol quote fallback;
  gate contextual consumers and expose dated freshness instead of claiming live data.
- `modules/premium_workspace.py`: gate live generation and cached result display;
  warn on suspect underlying bid/ask without promising executable prices.
- `modules/phase6_workspace.py`: preserve historical scenario use while warning
  against treating a saved stale/closed quote or close-seeded manual spot as live.
- `modules/public_research.py`: expose quote status and market-state metadata.
- `modules/public_data.py`: reconcile only the quote wrapper to the current shared
  provider; re-evaluate freshness on every Streamlit cache hit and retain clear().
- Restore deployed freshness tests and deterministic-clock selector tests without
  removing assertions; restore `docs/QUOTE_FRESHNESS.md` and ignore `diagnostics/`.

The four market/workspace/research modules, restored tests and freshness document
match the deployed versions. The public_data patch deliberately preserves all other
current methods and newer provider/index behavior. No API, MCP, auth, research
mathematics, archive reader, economics evaluator or dependency changes are needed.

## Intentionally excluded

Do not restore older API/MCP/provider files wholesale: doing so would remove the
three AlphaOS 2.0 tools, Phase 9/index compatibility, consumed-contract quality,
Supabase redaction and the newer research architecture. Older module removals,
collector differences and unrelated research/UI history are not ported. No current
security/freshness protection is dropped. No provider substitution, ranking,
execution, identity work, journal write, schema migration or schedule change.

## Compatibility acceptance

- `research_structure`: additive deterministic and validated completed-session
  historical metrics, provenance, fingerprints, sample sizes and missing reasons.
- `compare_structures`: same candidate economics plus shared contexts/fingerprints
  and explicit non-comparability, with unchanged deterministic fields and order.
- `run_market`: deterministic economics, capital status, shared temporal gates,
  overnight preference, and null unsupported historical/intraday/early-exit EV.
  Intraday entries do not become completed-close evidence as the clock advances.
- All 17 tools retain their contracts. REST/MCP parity is exercised through actual
  in-process HTTP/MCP authentication and fixture archive storage. Incomplete
  evidence never establishes eligible_for_consideration or a recommended winner.

Test commands/results are recorded in the PR. All data tests are fixtures, not
live Public/Supabase/Render validation. Local import, MCP lifespan startup/shutdown,
health and OpenAPI research route checks run with secret-file reads mocked.

## Deployment procedure — approval required, not performed

1. Review this one PR to main and its exact passing head SHA. Reconfirm main has
   not changed under it. Merge only with separate approval. If merge produces a
   different SHA, verify that SHA/tree and CI before selecting it for deployment.
2. On the existing Render service, keep automatic deployment disabled. Record
   existing manually selected deployment ID/SHA and settings for rollback.
3. Verify Python `.python-version` 3.12.14, no conflicting runtime override,
   build `pip install -r requirements-api.txt`, start `python -m alphaos_api`,
   health path `/health`, platform PORT and one instance/worker. Inspect presence
   only of ALPHAOS_API_TOKEN, ALPHAOS_PUBLIC_URL, PUBLIC_API_SECRET,
   PUBLIC_ACCOUNT_NUMBER, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY. Existing
   supported secret mounts remain valid for AlphaOS/Public credentials. Supabase
   configuration is environmental. Do not rotate/expose values or change settings
   without authorization. Preserve configured quote/archive freshness limits.
4. After separate deployment approval, manually select the exact approved SHA
   on the existing service. Do not use an unpinned latest-branch deployment.
   No migration command is part of API startup; do not apply any ledger SQL.
5. Verify deployed SHA, actual runtime and health, unauthenticated rejections,
   OAuth metadata and authenticated discovery of 17 MCP tools. Restarts revoke
   process-local grants; reconnect through existing consent as needed.
6. Check fresh/stale live quote behavior and safe latency diagnostics; check
   archive provenance and each of the three new research tools over authenticated
   REST and MCP. Missing archive/history is a typed blocker, not a reason to relax
   age limits. Intraday and early-exit EV must remain null. Complete an actual
   ChatGPT invocation before declaring connector verification complete.

## Rollback — approval required, not performed

Manually redeploy the previously recorded known-good immutable SHA (owner-supplied
baseline `cd59c2c4026a9505ecd25e1976da241b2dc4c534`) on the same service, preserving
configuration. Verify runtime, health, OAuth discovery and the tool inventory
expected for that older release. It predates the three new interfaces; do not
expect all 17 tools on rollback. Grants/snapshot IDs may require reconnection or
fresh requests after restart. No database rollback is needed because this release
applies no schema/data changes. Do not reverse migrations or alter stored archives.

## Release validation results

- Quote freshness, latency, quote MCP and selector tests: 76 passed.
- Archive/economics, REST/MCP, auth and configuration selection: 244 passed.
- Full `python -u -m pytest -q --tb=short --basetemp=.test-release-full`:
  722 passed, 40 subtests passed (220.95 seconds), no failures.
- Import/MCP lifespan startup/shutdown, health and OpenAPI route smoke: passed
  with secret-file reads mocked. Initial sandbox invocation stalled; outside the
  sandbox an obsolete route-introspection check was corrected to OpenAPI. No
  application workaround or regression-test weakening was required.
- `git diff --check`: passed. GitHub CI result and final SHA are in the PR.
