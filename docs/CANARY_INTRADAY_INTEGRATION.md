# Canary and intraday integration review

Base: main `7f7ef53c85151711ef5fdc3c5d092a7a3e6d84cb`.
Integration branch: `integration/canary-intraday-safety`.

## Order and scope

1. PR #31 `collector/verified-canary-wiring` at `b2bd429b4c5db919b417e8cf942bb4f65cb222aa`. This already includes PR #30's shared universe helper and tests (PR #30 head `27a9812d61269f0c1fda347f26fd43a5c6fc1178`). Do not apply the shared foundation twice.
2. All three PR #32 commits, ending at `e2bb6109c1adc7dcc81956f41251cfe8349c0d41`, from `research/intraday-session-integrity`.
3. Integration hardening rejects malformed contract buckets and absent/invalid quality markers rather than assuming clean evidence. Combined tests exercise the checksum-verifying archive reader before evaluation.

Both source PRs had passing CI when inspected. Cherry-picks were conflict-free. Original PR branches are unchanged. Strategy-engine, GitHub synchronization, API, MCP, authentication, schemas and deployment configuration are outside this change.

## Safety and limitations

Default collection remains SPY then QQQ. Only explicit `ALPHAOS_INTRADAY_CANARY=NVDA` or `IWM` adds one canary after core symbols. No flag is activated here. Existing retry, duplicate-slot, NYSE session and persistence paths remain in use. Canary collection does not expand the research archive reader's symbol allowlist.

The evaluator remains provider-free and descriptive-only, with conservative bid/ask cashflows and explicit fees. It rejects missing/untrustworthy quotes, incomplete collections, non-session evidence, stale or non-advancing quotes and asynchronous legs. It is not exposed as a new API/MCP tool. Its caller must use the existing checksum-verifying reader; a hash-shaped string alone is not storage verification. Fixture integration tests cover that boundary. No fills, POP, EV, recommendations or execution claims are introduced.

Live canary entitlement, rate limits, latency and private payload coverage remain unverified; collection costs grow with expiration count and retries. Activation requires a separate operational decision. This PR performs no live production verification or mutation.

## Validation

Focused command: `python -m pytest -q tests/test_canary_intraday_integration.py tests/test_canary_collector_integration.py tests/test_intraday_canary_universe.py tests/test_intraday_execution.py tests/test_intraday_quoted_round_trip.py tests/test_archive_read_path.py tests/test_research2_api.py`.

Full backend command: `python -m pytest -q` (existing PR CI workflow).

Local focused execution is blocked at collection by Windows Application Control rejecting a pandas native DLL, including outside the sandbox. This is not a passing test result. The draft integration PR's Linux CI is the validation authority; inspect its final result before approval. `git diff --check` passes.
