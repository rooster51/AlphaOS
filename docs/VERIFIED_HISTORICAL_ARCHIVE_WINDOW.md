# Verified historical archive windows

`modules.historical_archive_window.read_archive_window` is a read-only evidence
reader for SPY/QQQ. It does not evaluate a position, choose entry/exit quotes,
calculate P&L, or certify fills. It is not registered as a REST/MCP route. The
existing latest-snapshot reader, collector, immutable persistence, authentication,
research APIs and November paper pilot remain unchanged.

## Interface

```python
from modules.historical_archive_window import read_archive_window

result = read_archive_window(
    trusted_supabase_client,  # caller-owned SDK client; no credentials in payloads
    'SPY',
    '2026-11-03T15:00:00+00:00',
    '2026-11-03T15:10:00+00:00',
    expiration='2026-11-06',
    contracts=['SPY261106C00600000'],  # explicit, unique, canonical OSI IDs
    as_of='2026-11-03T16:00:00+00:00',
    max_quote_age_seconds=120,
    max_observation_age_seconds=600,
)
```

This example specifies a request shape, not a claim that production evidence
exists for these contracts. The injected SDK must support PostgREST exact counts
and Storage downloads. The lightweight latest-research HTTP transport is not an
accepted substitute; its different interface returns unknown metadata coverage.
There is no provider fallback or initialization of credentials in this module.

Timestamps must be timezone-aware. Invalid request identity, contract/expiration,
naive timestamps, future window relative to caller-supplied `as_of`, reversed
ranges, duplicate requested contracts or invalid policy numbers raise ValueError.
The caller supplies a trusted evaluation instant; the module does not read a wall
clock. At most 100 explicit contracts are accepted.

## Window and bounded-query rules

- `[start,end)` contains five-minute **slot starts**, with start inclusive and end
  exclusive. End may equal the exchange close. Both edges must be aligned.
- One regular NYSE session only, using the shared authoritative calendar and
  collector slot gate. Holidays, DST and early closes follow that calendar. The
  current supported archive policy is explicitly five-minute regular-session
  slots; no historical cadence is inferred from counts, candles or legacy rows.
- Multi-session, out-of-session or unaligned ranges return `unknown_coverage` with
  a reason and unknown expected count. Calendar failures do the same. Do not
  interpret unsupported schedules as zero expected observations.
- Select metadata by provider Public, exact symbol and slot range, ordered by
  slot/observation/id. Request at most 501 rows and an exact count; accept at most
  500. A count mismatch, unavailable exact count, unexpected slot, invalid shape
  or overflow returns unknown coverage. This detects server-side truncation as
  well as duplicates; no hidden pagination is treated as a complete window.
- Every expected slot is considered. Zero rows means missing; multiple rows means
  invalid duplicate evidence. There is no selection of a winner or older complete
  substitute. Unordered database results are returned in canonical slot order;
  actual observations must advance with slots. Reused metadata identity and
  nonadvancing observation timestamps are invalid.
- Nullable legacy slot timestamps cannot establish a slot and are never inferred
  or backfilled. They cannot make a supported expected slot verified.

## Verification and completeness

Each candidate's immutable compressed bytes are downloaded and SHA-256 checked
against metadata. The existing #79 metadata/envelope verifier is reused for
provider, symbol, session, observation/slot times, quality and contract count.
The archive path and payload schema are checked. This is read-only: no uploads,
upserts, record updates, deletion, archive replacement or quality reclassification.

The slot, payload, collection-start/generated/finish and creation timestamps must
be consistent: slot <= observation <= options collection start <= generated <=
finish <= metadata created <= as_of. Observation must fall inside the requested
window, finish must be no later than end and strictly before session close.
Observation-start lag from slot is at most 600 seconds by default. Stored
availability is checked at **as_of**, not claimed at the earlier market instant;
created_at is preserved for future no-lookahead consumers. This reader alone
never establishes that a trade could have been entered in real time.

Underlying identity, price and actual last-trade timestamp are required. Its
last-trade age at collection finish must satisfy the quote-age policy. Each
selected option quote requires:

- Exact requested canonical OSI root, date, call/put side and strike, matching
  the archived row and selected expiration. Another identifier is not substituted.
- The selected expiration is provider-requested, has exactly one recorded
  successful response interval and is absent from `expiration_failures`.
- A single non-rejected matching row with no rejection reasons, SUCCESS quote
  outcome and finite nonnegative uncrossed bid/ask, with a positive ask.
- Per-contract observation equal to the selected response receipt and inside its
  request interval; response is within the options collection interval.
- Both actual bid/ask timestamps, inside the regular session, nonfuture relative
  to contract observation and at most 120 seconds old there by default. Retrieval
  time and the read clock never replace either quote timestamp.

Both configurable age ceilings must be positive, finite and at most 900 seconds.
Historical observations do not become stale simply because they are read later;
all checks are against the historical source observation. Existing current-mode
freshness remains unchanged.

A snapshot must be marked **complete**, with consistent quality/count metadata,
and all selected contract checks must pass before `sufficient_evidence` is true.
Partial/empty snapshots remain insufficient even if the selected rows are valid.
Valid selected quotes in a partial snapshot are retained with the partial flag;
if a selected contract fails, no package of selected quotes is presented as valid.
Other valid slots remain available. Snapshot count changes alone do not establish
missing expirations. Received counts include pre-filter observations, so they are
not compared to the count of retained strike-filtered rows.

## Coverage result

Top-level fields include version, exact requested start/end, as_of, symbol,
provider, expiration, required contracts, policy, `slots`, `coverage` and
`lifecycle`. `read_only` is always true; **eligible_for_pnl is always false**.
No entry price, exit price, realized P&L or completed-trade result is generated.

| Field | Meaning |
|---|---|
| `coverage.status` | `complete_window`, `incomplete_window`, or `unknown_coverage` |
| `expected_slot_count` | Calendar/profile slot count; null if schedule cannot be established |
| `verified_slot_count` | Slots with a complete snapshot and all selected evidence verified |
| `missing_slot_count` | Empty expected slots after a proven complete metadata query; null on global unknown/query failure |
| `partial_slot_count` | Assessed partial/empty observations |
| `invalid_slot_count` | Invalid, duplicate or stale observations |
| `unknown_slot_count` | Assessed slots with unavailable private payloads; zero before per-slot assessment |
| `selected_expiration` | Selected-contract evidence status and verified slot count, separately from full snapshot quality |
| `reasons` | Sorted machine-readable reason codes, also supplied per slot |
| `lifecycle.sufficient` | Always false: evidence coverage does not validate a complete trade lifecycle |

Per-slot statuses are `verified_observation`, `partial_observation`,
`missing_observation`, `invalid_observation`, `stale_observation`, or
`unknown_observation`. Each has integrity/selected-expiration verification flags,
`sufficient_evidence`, reasons and (where verified) metadata plus selected quotes.
The metadata binds each quote to an immutable path, checksum, id and source.
Quote outcomes, timestamps and warnings are preserved. Displayed bid/ask sizes
are copied only if actually archived; neither sizes nor prices are defaulted.
Presence of a size field here does not certify its liquidity or fill eligibility.

Selected-expiration statuses are `complete_expiration_coverage`,
`partial_expiration_coverage`, or `unknown_evidence`. Complete selected evidence
inside a partial broader snapshot still leaves the slot/window insufficient.
No observations is unknown selected evidence; it is not proof that the provider
listed no contracts. Stale/invalid contracts have explicit slot reasons rather
than being labeled successful expiration evidence.

Examples of reasons: `selected_expiration_failed`, `selected_expiration_missing`,
`snapshot_incomplete`, `missing_observation`, `stale_observation`, `stale_quote`,
`missing_contract_leg`, `contract_identity_mismatch`, `duplicate_observation`,
`duplicate_contract_evidence`, `out_of_order_timestamps`, `checksum_mismatch`,
`payload_unavailable`, `invalid_contract_evidence`, and
`archive_metadata_unavailable_or_invalid`. Only fixed codes leave error boundaries;
SDK/provider exception bodies, URLs, credentials and response bodies are not logged.

`complete_window` is coverage for this explicit interval/expiration/contract set
under this policy. It is not complete provider universe coverage, full-session
coverage outside the interval, an executable quote, or a completed trade. Sparse
five-minute samples cannot establish intervening stops, market liquidity, atomic
multi-leg fills or a profitable strategy.

## Regression-first evidence and validation

All test market/store fixtures are synthetic. Before implementing the reader,
we reran PR #35 head `2fbbe5e` with its own immutable fixture reader: mark the
selected expiration failed in both entry and exit snapshots. It returned
`status=complete`, `pnl_dollars=198.0`; the required rejection/no-P&L assertion
failed. The new regression
`test_failed_selected_expiration_cannot_support_completed_pnl` uses the same
safety invariant (`assert_no_completed_pnl`), additionally asserting structured
incomplete coverage, selected failure, preserved good observations and unchanged
stored bytes/metadata. It now passes; #35 is not imported into production.

The new suite covers SPY/QQQ complete windows, missing slots, failed expirations,
partial/empty observations, checksum/corrupt/unavailable bytes, metadata mismatch,
query truncation, duplicates, out-of-order timestamps, stale/missing/future quotes,
contract mismatch/missing legs, calendar failures, early close and a 78-slot full
regular session. A real Supabase SDK with mocked HTTP transport verifies exact
count/query bounds and GET-only object downloads. No live data coverage or actual
private payload compatibility is asserted by these fixtures. Final test counts
are recorded in the PR.

## Remaining historical P&L blockers and next #75 remediation

Real SPY/QQQ compressed-byte/selected-contract coverage remains to be checked
through an authorized trusted runtime. Metadata-only completeness is insufficient.
Current normalized archives may lack displayed sizes; no values may be invented.
The SPY failed expiration/provider cause is not established by this implementation.
No collector or historical archive is changed to repair that evidence.

The subsequent bounded #75 remediation should remain a pure library: require
bid/ask timestamps to advance beyond entry quotes and entry cutoff, require
source observation/availability chronology, and reject reused or inconsistent
market observations. Segregate all summaries by immutable scenario/policy id,
deduplicate run/event identities, and test unresolved exits suppress performance.
Only after those tests pass should a separate trusted adapter connect this
reader's verified references to that engine, enforcing actual displayed size,
natural-side costs, selected entry/exit windows and conservative no-lookahead
rules. Window completeness alone must never authorize fills or realized P&L.

The November pilot remains three independent hypothetical $100 scenarios with
**$15/$25/$30 maximum entry debits**, no pooled performance, no unsupported
overnight positions and no live trades. #75's $50 default is not adopted.
No replay engine, portfolio ledger, orders, paper-pilot changes, schema changes,
API exposure, merge, PR closure or deployment is included here.
