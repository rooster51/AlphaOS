# SPY intraday immutable-slot retry investigation — November 3, 2026

## Evidence and baseline

The active collector workflow ran `main` at
`0c2a4b38eb08129b42de27c2c6689991e606a1f2`. This fix targets that baseline,
which already contains the noncanceling-heartbeat collector. It does not stack
on the unrelated UI/hosting branches or the older collector branches.

Read-only evidence:

- [Actions run 41669833642](https://github.com/rooster51/AlphaOS/actions/runs/41669833642),
  job 126034961243: at 16:01:49 UTC SPY failed at
  `supabase_option_snapshot`, runner line 82; at 16:01:59 it failed at
  `duplicate_check`, line 63. QQQ archived at 16:02:03, attempt 1, slot 16:00.
- Supabase metadata for November 3: SPY has 13 complete slots (2,882
  received contracts each) followed by five partial slots. Last complete slot
  is 15:35 UTC (10:35 a.m. ET); first partial is 15:40 UTC (10:40 a.m. ET).
  Partial counts at 15:40/15:45/15:50/15:55/16:00 UTC are
  2,540/2,540/2,536/2,540/2,540. QQQ has 18 complete slots, 2,617–2,618
  contracts. Each of these 36 metadata rows has a matching Storage catalog object.
  Catalog presence does not verify private object contents.
- First partial object:
  `options/symbol=SPY/date=2026-11-03/20261103T154000+0000.json.gz`,
  recorded SHA-256 `06870c26cd2a70b74ea703fed2a79a510f30938779d1fd508919dca004193987`.
- 16:00 partial object:
  `options/symbol=SPY/date=2026-11-03/20261103T160000+0000.json.gz`,
  recorded SHA-256 `8361e532b26f08e7a16e04462f0a00c98b48102a4852f8b42816d3d2cea858b4`.

These are recorded metadata hashes, not an independent verification of the
production bytes. No credentials were retrieved or changed. Local collector
credentials are absent, and the connected Supabase tools do not expose private
Storage downloads. No production snapshot was downloaded, deleted, rewritten,
reclassified or backfilled.

## Two distinct causes

**Collection quality:** `build_options_snapshot` sets `partial` when an
expiration collection fails or expiration discovery contains invalid entries.
A failed expiration can mean provider/network failure, invalid calls/puts shape,
or an exception while normalizing that expiration; the historical broad catch
records only `chain_retrieval_failed`. Received contract count is measured before
strike filtering and includes rejected contracts. Neither a count reduction nor
stale/missing quote fields alone sets `partial`. A successful smaller response
can still be complete under this existing policy; completeness is not a provider
universe guarantee or a claim that every contract is usable for research.

The loss of 342–346 observations is consistent with an omitted expiration,
but metadata and sanitized logs cannot prove which expiration failed, an HTTP
status, rate limiting, an entitlement issue, or distinguish it from malformed
discovery. Definitive diagnosis requires an authorized read of the preserved
checksummed payloads: compare `expiration_failures`, `invalid_expiration_count`,
`requested_expirations`, `requests`, discovery and per-expiration record counts
against the last complete snapshot. Even those payloads may not contain the
underlying provider exception. This PR does not invent that missing evidence.

**Retry control flow:** persistence intentionally archives partial evidence and
returns its quality. The runner correctly rejects it as success, but then slept
and retried. The unique slot and immutable object already belonged to that
partial observation. Retry found the same row and raised another error. Repeated
collection or an overwrite cannot safely repair that slot. The observed errors
are deliberate quality rejection, not proof of a Supabase outage.

## Correction

- Treat a persisted or previously verified incomplete slot as terminal for that
  symbol's current slot. Report failure, skip the futile sleep/retry and continue
  to QQQ. A later slot can collect normally. Transient failures still get at most
  two attempts within the original slot/session gates.
- Verify duplicate-slot evidence before returning it: require exactly one row,
  download its existing object, verify compressed-byte SHA-256 and metadata/payload
  identity, observation/slot timestamps, quality and contract count. Missing,
  inconsistent or unreadable evidence fails closed. A complete metadata label
  cannot hide a partial object.
- Validate quality before uploading. Following an upload error, retain existing
  first-object-wins recovery; use that exact object's payload and checksum,
  including partial/empty status. Keep `x-upsert: false` and metadata
  `ignore_duplicates=True`. Require the persisted readback to match the canonical
  object, rather than accepting an unrelated/conflicting row as success.
- Emit only nonnegative numeric contract/failed-expiration/invalid-expiration
  counts for new incomplete collections; no response/error bodies or credentials.

No archive paths, payload serialization/checksum scheme, schema, freshness policy,
research reader, quote validation, symbols, collection universe, workflow,
timeouts, UI, hosting, secrets or execution paths change. Duplicate verification
adds one existing-object read; an unavailable object now prevents duplicate
success. Recovery never selects an older complete snapshot to hide newer partial
evidence. Existing partial slots remain failed and immutable by design.

[Supabase's standard-upload contract](https://supabase.com/docs/guides/storage/uploads/standard-uploads)
confirms that default uploads preserve an existing object; setting upsert would
replace it. The current changelog was reviewed; no Storage API change is needed.

## Regression validation

Synthetic storage/provider tests cover partial/empty first attempts, repeated
invocations, complete duplicates, lost metadata acknowledgements, object-only
commits followed by retries, immutable conflict recovery (including an improved
second response losing to the partial first object), corrupt/mismatched evidence,
conflicting metadata quality, pre-upload quality validation, and independent
SPY/QQQ outcomes. Builder tests distinguish failed chains/malformed expirations
from merely smaller successful responses. Existing archive reader tests retain
checksum, current/historical freshness and fail-closed behavior.

Validation results are recorded in the PR. No deployment, merge, collector
workflow dispatch, live provider request, live archive write or trade was made.

Local validation on Python 3.12.14, commit `a5883da` (documentation-only result
recording follows):

- Focused collector/reader/provider/coverage/adapter selection: **110 passed**.
- Full suite: **1,338 passed + 64 subtests passed**, two failures because the local
  environment lacked the real Supabase SDK (`ImportError: create_client`).
- Installed the already-declared `supabase==2.32.0` in an isolated test environment;
  reran both affected test modules together with the focused selection:
  **143 passed** in 24.29 seconds. This includes both previously failing tests.
  The entire full suite was not repeated after installing that dependency.
- Earlier setup attempts exposed Windows pytest-temp permissions and child-process
  dependency-path problems; the isolated environment and a dedicated writable
  basetemp resolved those without repository changes.
- Compile checks and `git diff --check` passed. Only existing Starlette/Supabase
  deprecation warnings remain in the final selected run.
