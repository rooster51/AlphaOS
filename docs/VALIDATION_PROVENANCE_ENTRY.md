# Validation: verified provenance into entry evidence

Status: **integration validation only.** No merge, deployment, infrastructure,
credential or data-retention change. All fixtures are synthetic; no Public or
Supabase request was made.

## Commits tested

| Ref | Commit | Note |
| --- | --- | --- |
| `main` | `77ef046` | PR #66 merged; current base |
| PR #68 | `9c79fcb` | `research/verified-quote-provenance` |
| PR #69 | `7377e9e` | `feature/entry-evidence-record` |
| PR #67 | `b93c2a2` | `codex/cloudflare-workers`, context only, unmodified |
| `validation/provenance-entry-integration` | cherry-picks of `9c79fcb` and `7377e9e` | integration branch |

Both PRs are single commits on `77ef046`, so they were cherry-picked in order.
**No conflicts occurred** and no conflict resolution was needed. Neither source
branch was modified.

## Chain exercised

`archive record {payload, metadata, freshness}` → `resolve_structure()` →
`market_data` evidence → `build_entry_record()` → immutable entry record.

`tests/test_provenance_entry_integration.py` replaces only the archive read with
a hand-built record having the same shape; the two functions run unmodified.

## Results

- Integration suite: **26 passed**.
- Provenance + entry suites together: **100 passed**, no skips (the version-drift
  guard executes and passes once PR #68 is present).
- Full regression: **1310 passed, 64 subtests passed, 0 skipped, 0 failed** in
  299.15 s.
- Dependency files (`requirements*.txt`, `web/package*.json`): unchanged.

Confirmed by the integration tests: contract/strike/expiration/type/quantity are
unchanged end to end; bid/ask and both timestamps are preserved with no
recalculation or mid-pricing; every leg cites the same snapshot id; buy-ask /
sell-bid remains the pricing basis; package cashflow equals the payoff engine's
input on every scenario; snapshot, symbol, date, spot, cashflow and quote-age
checks stay enforced; hypothetical evidence cannot become an entry record; a
`verified_for_trading` claim is refused; and the entry builder is not imported by
the HTTP or MCP surface.

## Defects found

1. **Entry record dropped leg provenance (moderate, fixed).** `build_entry_record`
   emitted legs without `symbol`, `expiration`, `snapshot_id` or
   `observation_timestamp`, so a record could not prove which snapshot its legs
   came from. Unit tests did not catch it because they only exercised fields the
   record already carried; the end-to-end test did. Fixed on the integration
   branch and covered by assertions on all four fields.
2. **Future-dated quote surfaces a contract code, not a stale one (low, documented).**
   The archive adapter excludes contract rows whose timestamps post-date
   collection completion, so the contract is gone before quote-age validation
   runs; the caller sees `market_contract_mismatch`. The package is still refused;
   only the reason code differs from the nominal `market_quote_stale`. The test
   records this behaviour rather than weakening it.

## Trust boundary

`StructureLeg` forbids unknown fields, so bid/ask, timestamps or a verification
flag cannot be submitted; `market_data` carries only a snapshot id and checksum;
the server re-reads the archive through the checksum-verifying reader before
producing evidence. `build_entry_record` has no HTTP, MCP or website caller and
cannot be reached with client JSON.

## Cloudflare compatibility (PR #67 review only)

The combined change introduces no Worker storage, calculation or cache, no new
environment variable (the website still uses only `ALPHAOS_API_URL` and
`ALPHAOS_API_TOKEN`), no new dependency and no paid service. Render remains the
research engine, Supabase the archive, MCP the ChatGPT interface, and the website
a presenter. PR #67 was not modified or deployed.

## Remaining blockers

1. PR #69 remains unwired: nothing calls `build_entry_record` until a follow-up
   decides where the structure path invokes it.
2. PR #67 and PR #68 both edit `web/src/lib/structure-bridge.ts` and
   `StructureWorkbench.tsx`; whichever merges second needs a rebase and a browser
   pass. Not tested here because #67 is out of scope.
3. Staging validation against real fresh SPY/QQQ data and the deployed MCP
   connector remains outstanding for PR #68; synthetic parity is not real-market
   validation.
4. No historical settlement, POP, EV or ranking work exists on this branch.
