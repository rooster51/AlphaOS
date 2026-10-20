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

## Final integration review (2026-10-12)

Reviewed PR #33 at `3589353f307c20210e77ded4857e097a28f0201f` against unchanged main `7f7ef53c85151711ef5fdc3c5d092a7a3e6d84cb`; CI run 38190412153 passed 782 tests and 40 subtests. Collector defaults, canary opt-in, private storage reader, session checks and evaluator inputs were inspected directly.

Found and fixed one temporal defect: an advancing exit quote could still precede the requested entry cutoff under a sufficiently long quote-age policy. Both exit bid and ask must now be strictly after entry_as_of, in addition to advancing relative to entry quotes. Four regressions cover either side before or exactly at entry. No freshness limit was extended.

`tests/test_historical_archive_boundary.py` adds 16 cases using the actual collect_symbol/build_options_snapshot normalizers, persistence-equivalent compressed bytes, the real read_latest_option_snapshot function and the evaluator. Coverage includes SPY/QQQ calls/puts, long/short cashflows and fees, exact envelope keys, unchanged input provenance, separate slot/collection/cutoff timestamps, cutoff query predicates, partial quotes, mismatched terms, late insertion, future completion, slot mismatch, corrupted bytes and stale observations. Storage/database transport is a read-only fixture; these are not production results.

### Real archive access and next integration gate

Read-only production SQL on 2026-10-12 found 312 metadata rows each for SPY and QQQ during October 5-9, all matching Storage catalog objects. October 9 has 78 per symbol, October 7 only 74. No NVDA/IWM rows were returned. Object catalog presence is not a downloaded-payload or SHA-256 verification.

The existing archive_client requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY; neither is present in this execution environment. The connected Supabase tools provide SQL metadata access but no private-object download operation. No secrets were retrieved, credentials changed, or alternate privileged SQL/network mechanism used to bypass this boundary. Therefore actual private payload compatibility and quote completeness remain unverified. Private downloads require an authorized server-side client with Storage SELECT access: https://supabase.com/docs/reference/python/storage-from-download .

Next concrete gate: in an already authorized credentialed runtime, call read_latest_option_snapshot for predetermined entry and exit cutoffs with an explicit archive-age policy. Pass its envelopes directly to reconstruct_quoted_round_trip, keeping quote-age policy separate. Retain each metadata id, archive_path, archive_sha256, slot_time, observed_at, created_at, collection_finished_at, request cutoff and evaluator policy beside the result. Do not rewrite the bytes or relabel slot time as quote time. The reader uses both observed_at and created_at <= each historical cutoff; late-created backfills cannot masquerade as contemporaneously available evidence. Reject partial/unusable evidence rather than searching forward or silently substituting older usable quotes. Choose contracts and entry rules without examining future exits; missing exits remain missing, never discarded to inflate performance.

No storage/API entry point, strategy selection, batch statistics, fill model, POP, touch rate or EV is introduced here. Real-payload verification remains a gate for that later milestone, not a reason to activate canaries or weaken evidence checks.

Final-review focused command: `python -m pytest -q tests/test_historical_archive_boundary.py tests/test_intraday_quoted_round_trip.py tests/test_canary_intraday_integration.py tests/test_canary_collector_integration.py tests/test_intraday_execution.py tests/test_archive_read_path.py` — 107 passed in 99.73 seconds. Python compile checks and git diff --check passed. The prior Windows DLL failure did not recur in this run. Final full-suite results are recorded on the PR for its exact head SHA.
