# Entry evidence record (Milestone 1)

Status: **library only, no caller, not deployed, not exposed.** This is the first
step of the historical calibration plan
([HISTORICAL_CALIBRATION_PLAN.md](HISTORICAL_CALIBRATION_PLAN.md), milestone M1).
It adds no HTTP route, no MCP tool, no website surface and no persistence.

## What it is

`modules.entry_evidence.build_entry_record(trade, evidence)` turns a verified
archive-backed structure into one deterministic "here is exactly what was
entered" record: the snapshot identity and checksum, the underlying price and
time, every selected contract with both sides of its quote and both timestamps,
the chosen entry side and price, the signed package cashflow and the fees.

It is the entry half of an entry-to-exit pair. The exit half is milestone M2 and
does not exist yet, which is why the record contains no outcome field at all.

## Trust boundary: why this does not duplicate verification

Archive verification already exists in `modules/structure_provenance`
(PR #68, `resolve_structure`). That function owns the snapshot read, the
checksum comparison against the metadata row, the OSI-versus-snapshot identity
match, bid/ask usability against the archived rows, and quote ages against the
request instant.

This module does **not** re-do any of that. It never opens the archive, never
downloads an object, never re-derives a quote and never asserts a price is the
market's. It consumes the verifier's output and checks the properties that make
it usable as a record:

| Owned by the verifier (PR #68) | Owned here |
| --- | --- |
| Archive read, checksum, path/identity | Record shape and single-snapshot binding |
| OSI contract exists once in the snapshot | Contracts unique within the package |
| Bid/ask usable in the archived row | Entry side/price consistent with quantity sign |
| Quote age against the request time | Ages consistent with the stated age fields |
| Cashflow equals natural bid/ask package | Cashflow equals the researched trade |
| — | Evidence cannot claim to be trade-ready |

That split is deliberate. Re-implementing archive checks here would create a
second authority that can drift and, worse, could pass something the verifier
would reject. Instead this layer can only be *stricter*: it rejects anything
internally inconsistent, and it cannot promote evidence the verifier marked
`verified_for_trading: false`.

## Contract

Input `trade`: the already-normalized option trade (`symbol`, `expiration`,
`spot`, signed `credit`, `fees`, and legs carrying `type`, `strike`, `qty` and
`contract`). Input `evidence`: the `market_data` object from the verified
structure response.

Output: a JSON-safe record with

- `version: "entry-evidence-v1"`, `record_type: "entry"`,
  `evidence_version: "structure-market-data-v1"`;
- `symbol`, `expiration`, `session_date`, `multiplier: 100`, `shares: 0`, `spot`;
- `pricing: "natural_bid_ask"`, `signed_package_cashflow` (echoed, never
  recomputed from a model), `fees` (echoed);
- `snapshot` — id, provider, symbol, session date, observation/slot/creation
  times, archive path, SHA-256, quality status;
- `verification` — evaluation instant, quote age ceiling, underlying age and,
  when the verifier supplied it, archive age;
- `legs[]` — input order, with index, type, strike, quantity, contract, symbol,
  expiration, the snapshot it came from, observation timestamp, entry side and
  price, bid, ask, both quote timestamps, archive quality, warnings and ages;
- `research_only: true`, `verified_for_trading: false`, caveats;
- `fingerprint` — SHA-256 over the canonical JSON of everything above.

The reference instant is the payload's own `evaluated_at`. The module never reads
a clock, so the same inputs always produce byte-identical output.

## Rejection codes

Stable and safe to quote; no payload contents appear in an error.

`entry_payload_invalid`, `entry_evidence_not_verified`,
`entry_trade_ready_claim`, `entry_pricing_unsupported`,
`entry_snapshot_incomplete`, `entry_snapshot_mismatch`, `entry_timestamp_invalid`,
`entry_contract_missing`, `entry_contract_invalid`, `entry_contract_duplicate`,
`entry_contract_mismatch`, `entry_leg_count_mismatch`, `entry_leg_mismatch`,
`entry_quote_invalid`, `entry_quote_stale`, `entry_cashflow_mismatch`,
`entry_fees_invalid`, `entry_shares_unsupported`, `entry_multiplier_unsupported`,
`entry_spot_mismatch`.

Notable rejections: a payload whose `verified_for_trading` is not exactly `false`
is refused rather than silently downgraded, because promoting it later would be
a one-line mistake; a leg citing a different snapshot than the package is
refused, because that is how two snapshots get mixed into one supposedly
single-observation record; and a reported age that disagrees with the timestamps
is refused, because the age fields are what a later evaluator would trust.

## What this deliberately does not do

No replay of past snapshots, no exit or settlement, no POP, no EV, no ranking, no
storage, no REST or MCP field, no website change, no new dependency, no change to
the payoff engine, archive validation, freshness policy or the 12-second market
timeout. The existing economics remain authoritative: the record echoes the
trade's cashflow, fees and legs, and a test asserts that `premium_engine.payoff`
returns the same value for the record as for the original trade.

## Dependency on PR #68

The record consumes the `structure-market-data-v1` payload, which exists only on
PR #68's branch. Until that PR merges, nothing in this repository produces such a
payload, so this module has no caller. It is safe to merge independently — it
ships dark — but it cannot be wired up before #68 lands. A test compares its
`EVIDENCE_VERSION` constant with `modules.structure_provenance.VERSION` when that
module is importable, so a future schema rename fails loudly instead of silently
accepting a stale payload.

## Tests

`tests/test_entry_evidence.py` — 63 cases over a synthetic QQQ debit spread and a
SPY put credit spread: happy path, determinism, fingerprint stability under key
reordering, input immutability, payoff equivalence, the full rejection matrix, a
purity check over the module's imports and file access, and the version-drift
guard. 62 execute on this branch; the guard skips until PR #68 is present. All
fixtures are constructed in the test file; no archive, Supabase or provider data
is used.
