# Verified contract and quote provenance

This focused change builds on PR #66 (`77ef046`) and the October 27 audit in
PR #67 (`b93c2a2`). It does not include or modify PR #67's Cloudflare deployment
work. The earlier audit established scenario arithmetic, but the public request
schema discarded contract identities and therefore could not verify price inputs.

## Request modes and trust boundary

Existing `/v1/research/structure` and `/v1/research/structures/compare` requests
remain hypothetical when `market_data` is absent/null. They use the supplied
spot, cashflow and fees. Their response explicitly reports
`evidence.market_data.kind = hypothetical`, `verified = false` and
`verified_for_trading = false`. Old website envelopes remain displayable as
hypothetical; missing provenance can never satisfy an archive-backed request.

Archive-backed requests add:

```json
{
  "market_data": {
    "snapshot_id": "<id from archive.storage.id>",
    "archive_sha256": "<archive.storage.archive_sha256>"
  },
  "legs": [
    {"type": "Call", "strike": 500, "qty": 1, "contract": "QQQ300102C00500000"}
  ]
}
```

This is a **partial synthetic schema example**, not a listed contract claim or
trade input. Supply all existing required fields: symbol, expiration, as_of,
spot, signed package credit, fees and supported legs. Obtain actual references
and contracts from the existing archive-backed market research response:
`research.archive.storage` and selected candidates' quote-bearing legs. The
observation-only prefill returns no option quotes and does not certify a scenario.

Clients cannot submit bid/ask values, quote timestamps, a verification flag, a
storage URL or a replacement data source. Every archive-backed leg must include
its contract; contract IDs without a reference and partially identified packages
are rejected. Server-held credentials remain in the existing archive reader.

The server re-reads the **latest** snapshot through the existing checksum,
metadata/path/identity and freshness checks. It does not fetch an arbitrary ID,
change the collector, call a live chain as fallback, or alter the archive. The
requested ID AND checksum must match. Snapshot rollover requires the caller to
obtain and explicitly review new evidence; there is no silent repricing.

## Leg and package validation

- One snapshot/provider, symbol, expiration and current New York session date
  per strategy. Cross-symbol/date comparisons retain separate per-candidate
  context; a single strategy cannot mix those contexts.
- Unique selected identities; exactly one archived occurrence, including checks
  across rejected buckets. OSI root, expiration, call/put and strike must agree
  with both the request and archived row. Collection-failed/rejected rows cannot
  be promoted. A partial archive can support a package only when every selected
  leg independently passes.
- Finite, nonnegative, uncrossed bid/ask, positive ask, explicit timezone-aware
  timestamps on BOTH sides. Quotes and underlying must be no more than 900
  seconds old at server evaluation and cannot be future-dated. Underlying time
  cannot follow archive collection completion. Existing archive age policy is
  unchanged (default 600 seconds); archive freshness and quote freshness differ.
- Spot must match the archived underlying. Signed package credit must equal
  `-sum(qty × ask for buys / bid for sells)`, within `1e-8` dollars/share for
  numeric representation. Decimal arithmetic avoids package accumulation drift.
  Fees remain explicit user-supplied total package dollars, not certified costs.
- The existing payoff engine owns all economics. No pricing model, POP, EV,
  ranking, strategy, holding policy or broker buying-power claim is introduced.

Comparisons pin one trusted read per symbol and one evaluation time, avoiding a
snapshot changing between candidates in one request. Any invalid archive-backed
candidate rejects the whole request, including mixed hypothetical/verified lists.

## Response and website behavior

The additive evidence schema is `structure-market-data-v1`, inside the existing
`alphaos-interface-v2` envelope. Verified archive results carry:

- `kind: verified_archive`, `verified: true`, **`verified_for_trading: false`**;
- snapshot ID, provider, symbol, checksum, archive path, session/observation/slot/
  creation times and quality status, plus the reader's archive freshness;
- underlying price/time and evaluation time;
- every selected contract, strike, expiration, type, quantity, bid/ask, quote
  timestamps, archive quality/warnings, chosen entry side/price, snapshot ID and
  bid/ask age policy/results;
- natural bid/ask package cashflow, explicit fees and fill/margin limitations.

Quote-bearing identity survives normalized position legs and payoff trade legs.
Comparison's descriptive projection preserves each candidate's full market-data
evidence alongside the full researched candidate. Input order is not preference;
winner and recommendation remain null. Presence of a quote field alone remains
distinct from the new explicit archive-verification status.

REST and OAuth MCP use the same Pydantic request models, service and sanitized
response path. MCP tool descriptions document the modes and failure behavior.
The website BFF forwards the same references and rejects responses with dropped,
contradictory, stale, or mismatched provenance. The browser independently binds
the response to the submitted scenario and reference. Single and comparison
views display contract bid/ask timestamps, evaluation ages, snapshot ID/checksum
and a prominent distinction from hypothetical scenarios and executable fills.

The Structure Lab checkbox enables archive-backed validation, with snapshot and
contract fields. Saved comparison payloads retain the selected mode/reference.
Selecting hypothetical mode is an explicit user action; errors do not switch it.
Existing manual forms, observation prefill and scenario economics remain intact.

## Safe failures

Invalid request shapes return 422 at REST/MCP validation (400 at the website
input boundary). Stable service error codes distinguish `archive_snapshot_mismatch`,
`archive_expiration_unavailable`, `market_contract_mismatch`,
`market_data_spot_mismatch`, `market_data_cashflow_mismatch`,
`market_data_date_mismatch`, `market_quote_invalid` and `market_quote_stale`.
Archive read failures preserve existing `archive_missing`, `archive_stale` or
`archive_unavailable` codes. Unexpected resolver failures return the safe
`market_data_unavailable` code, never exception text or credentials. The website
maps these to explicit errors and displays no substitute economics.

## Validation and release gates

Regression/integration coverage uses **synthetic, labeled test archives**, never
pretends fixtures are live observations. It exercises every existing strategy
representation (11) × SPY/QQQ × 0DTE, weekly, monthly and >365-day dates through
authenticated REST and OAuth MCP; checks full comparison provenance, original
payoff equivalence, mixed modes, pinned reads and integrity failures. A committed
canonical REST/MCP fixture is consumed by website route/client and browser tests;
a Python test prevents fixture/schema drift. Gzip fixture headers are explicitly
portable; real storage checksums are unchanged.

Run the normal Python, web unit, typecheck, build and browser suites. Exact local
results are recorded in the development PR. No new dependency or CI service is
needed: the existing PR workflow already runs these tests.

Remaining limitations and gates:

1. **Current snapshots only.** Archive-backed explicit structures require current
   session dates and quote freshness. Historical replay needs a separately
   reviewed contract; old archive IDs are not accepted by relaxing freshness.
2. **Natural prices only.** Existing market discovery can use midpoint/rounded
   debit scenarios. Those original scenarios remain unchanged, but must not be
   relabeled verified by this path. Explicitly review matching natural prices
   before submitting an archive-backed structure; midpoint mismatches fail closed.
3. **Evidence is not execution.** Provider delay, simultaneous liquidity across
   legs, fills/slippage, actual fees, assignment, and account margin remain
   unverified. POP/EV calibration and opportunity ranking remain separate gates.
4. **No deployment performed.** Verify this branch against staged Render and a
   compatible website before release. PR #67 remains independent/open; its
   Cloudflare production and Render cold-start gates remain outstanding. The
   existing 12-second market timeout is unchanged. Live MCP parity also requires
   the owner's existing connection to be authenticated; local OAuth parity is not
   a claim that the deployed connector has been updated.

No credentials, infrastructure changes, collector changes or production release
are required to review this PR.
