# Issue #56: SPY/QQQ expiration coverage audit and bounded expansion

Base: main after PR #55 (`b0ed8f6`). Audit date: October 20, 2026.
Draft only. No deployment, workflow dispatch, infrastructure/schema change,
subscription, credential, paid service, timeout, symbol or strategy change.
**Milestone 1 production cold-start acceptance remains open.**

## What the existing system actually collects

`scripts.run_intraday_snapshot` uses `DailyPublicProvider` with the existing Public
account, during the existing NYSE regular-session gate. Its raw market-data POSTs
discover expirations and retrieve one chain per exact date. These are read-only
market-data operations, not trading POSTs. `build_options_snapshot` validates OSI
identity, side, strike, dates, outcome, bid/ask and timestamps. It retains separate
valid/questionable/rejected observations and then applies a spot-relative strike
band. `collect_symbol` wraps the observations in `intraday-archive-v1`.

Before this PR, `config/intraday_archive.json` retained only **0–7 calendar DTE**
and **±5% of the underlying last price**. Therefore an expiration offered by Public
outside seven days was never fetched, and most deep ITM/OTM strikes were discarded
even in fetched chains. Invalid/rejected contracts are retained for diagnostics;
otherwise-valid out-of-band strikes are counted but not stored individually.
`received_contract_count` counts returned rows before these filters, not usable
quotes or candidates. A complete snapshot means collection succeeded, not that
every contract is liquid, fresh, or research-eligible.

The separate daily artifact pipeline uses **0–10 DTE / ±10%** and validates its
config at a maximum of 365 DTE. It produces separate daily artifacts; the API's
verified intraday reader does not substitute them. Its settings remain unchanged.

The GitHub workflow already has a 15-minute job limit and a 720-second collector
command budget. No schedule, concurrency, command budget or infrastructure is
changed. Each symbol retains independent collection/slot timestamps. Extending
every expiration and every strike on every heartbeat would increase network,
archive size, collection duration and freshness risk; this PR does not do that.

## Production evidence versus unavailable audit evidence

A read-only SQL query against the existing AlphaOS Supabase project returned:

| Symbol | Latest observed UTC | Provider | Metadata DTE window | Strike band | Received rows | Status |
|---|---|---|---|---|---:|---|
| SPY | 2026-10-20 19:55:58.594933 | Public | 0–7 | ±5% | 1,824 | complete |
| QQQ | 2026-10-20 19:56:01.058478 | Public | 0–7 | ±5% | 2,254 | complete |

The two preceding pairs also used those settings. This confirms deployed policy
and collection activity. It does **not** reveal the exact expiry list, returned
strike endpoints, discarded strike endpoints, bid/ask timestamps, entitlements,
or freshness at the time of this audit. No archive bytes or checksums were bypassed
to obtain stronger claims from metadata.

Both connected AlphaOS `option_expirations` calls returned a reauthentication
requirement. No local Public credentials were configured. Two historical website
audit calls reached the local 20-second read timeout and provided no usable body;
this did not change any website/backend timeout. The new read-only audit command
also returned `provider_authentication_or_configuration_unavailable`. Consequently
**live monthly/LEAPS dates, strikes, quote timestamps and account-specific access
are not verified in this PR**. Reconnecting the existing account is needed for
that evidence; no subscription or credential change was attempted.

Public documents exact expiration discovery and chain retrieval under its existing
`marketdata` scope for individual investors. The inspected docs specify an exact
`expirationDate` and return calls/puts with strikes/quote fields; they do not
guarantee this account a particular monthly/LEAPS date range, strike universe,
latency, real-time entitlement or rate limit. No extra paid entitlement is assumed.

## Implemented improvement

The intraday repository config enables `extended_expiration_coverage`. With it:

1. Preserve every provider-listed, eligible expiration in the existing 0–7 DTE
   window and the existing ±5% strike band.
2. Add **at most one** earliest additional standard monthly calendar date and
   **at most one** earliest additional long-dated date (at least 365 calendar days).
   Both must be present in Public's actual discovery response and be exchange
   sessions on/after the observation date. No date is manufactured or substituted.
3. Keep per-chain failures explicit and the archive partial when a chain fails.
   Do not replace a failed requested date with another discovered chain.
4. Record the provider discovery list, excluded/invalid counts and bounded policy
   in the checksummed archive payload. The existing SQL `min_dte`/`max_dte` fields
   continue to describe the **base** window; the payload's universe and discovery
   policy describe the extended selections. No database migration is required.

This adds at most two chain calls per symbol per collection attempt (four per
SPY/QQQ pair). Existing runner retry behavior is unchanged and can repeat an
attempt. No new collection is triggered by this PR. It supports representative
monthly/long-dated coverage after deployment and successful collection, not every
monthly or LEAPS expiry, and not every strike. Setting the new config flag false
retains the prior DTE-window selection behavior; daily collection defaults are
unchanged. Calendar-invalid dates in enabled extended collection are rejected.

The research adapter returns `archive.expiration_coverage`, describing archived
observations by exact date and horizon. Failed, empty or invalid dates remain
`missing_verified_evidence`; absence of a provider horizon is not falsely called
an unsupported subscription. These labels do not promote quotes or candidates.
All existing chain/quote/liquidity, routing, capital, checksum, identity and
freshness gates still run. Current requests never search an older snapshot to
find a desired date. Historical mode remains explicit and labeled.

## Calendar labels and exact-date semantics

The following labels are research conventions, not certified exchange series:

| Label | Definition, in precedence order |
|---|---|
| 0DTE | Expiration equals the archive's New York session date |
| 1DTE | Exactly one calendar day later |
| Long-dated / LEAPS-style | At least 365 calendar days later; not proof of official LEAPS series status |
| Monthly | Third Friday, or last NYSE session on/before it if closed, below 365 DTE |
| Weekly | Other eligible listed date 2–7 calendar days later; not a certification of a weekly series |
| Other | Other eligible provider-listed date; not silently recategorized or collected beyond the policy |

An additional `calendar_kind` retains monthly-date identity even when the primary
horizon is 0DTE, 1DTE or long-dated. Friday-to-Monday is three calendar DTE, not 1DTE.
Good Friday shifts the monthly calendar date to Thursday; it never creates a
provider expiration. Weekend/holiday explicit expirations are rejected even if
an invalid archive lists them. The calendar package's future-session assumptions
remain subject to exchange changes.

Omitting expiration preserves existing first-archive-date selection. An explicit
date must match this verified snapshot; absent dates produce HTTP 422 with
`archive_expiration_unavailable`. A requested-but-failed/empty chain cannot create
candidates and its coverage status is missing evidence. The website forwards
the date unchanged and rejects responses whose request/research/session dates
disagree. The UI supports exact-date entry and a coverage table; suggested dates
use nonfailed archived observations where coverage metadata is supplied. OAuth
MCP uses the identical request model/service; no new tool or endpoint is added.

## Capability matrix: production versus contract verification

| Horizon | SPY production evidence today | QQQ production evidence today | This PR's local contract verification | Remaining limitation |
|---|---|---|---|---|
| 0DTE | 0–7 policy confirmed; exact chain/timestamps unverified in this audit | Same | Collector → checksum reader → REST/MCP tested | Date must actually be listed and quotes usable |
| 1DTE | Same | Same | Both symbols, exact date tested | Calendar day, not next trading session |
| Weekly | Same | Same | Both symbols, exact date tested | Only base-window provider dates; not all weekly series |
| Monthly | Blocked by deployed 0–7 policy when outside window; live access unverified | Same | Both symbols; Good Friday boundary; website fixture and bridge tests | At most one additional monthly; needs new successful collection |
| Long-dated | Blocked by deployed 0–7 policy; live entitlement/chain unverified | Same | Both symbols; >=365-day chain/REST/MCP and website tests | At most one additional date; no LEAPS-brand guarantee; narrow strikes |

“Tested” means synthetic fixture contracts, not verified working production
quotes. Actual dates/endpoints and per-contract timestamp quality remain blocked
pending authenticated read-only provider/verified-archive inspection. No production
long-dated coverage is claimed merely because Public documents an expiration API.

## Economics and data limitations

- Standard same-expiration 100-share option economics are unchanged. Natural
  bid/ask pricing, payoff functions, costs, risk limits and exclusions are reused.
  No probability calibration or EV is added for longer horizons. Existing daily
  historical horizons are bounded; unsupported/unaligned economics stay missing.
- Expiration payoff is not early-exit pricing, margin/broker buying power,
  American early-exercise/assignment or dividend/funding modeling. Deep-ITM
  long-dated strikes outside ±5% still cannot be researched from this archive.
- Collection time never replaces provider bid/ask timestamps. Missing, previous-
  session, invalid/future timestamps retain the existing warnings/rejections.
  Archive age is not proof that every individual contract quote is fresh.
- Public's current documentation describes Black–Scholes Greeks and a separate
  American-exercise IV inversion (Bjerksund–Stensland), with midpoint/last-trade
  input conventions. These provider model estimates are retained, not recomputed
  or interpreted as probabilities. The audit could not verify their availability
  for this account's long-dated contracts. AlphaOS expiration payoff calculations
  do not become a valuation/early-exercise model by collecting more expirations.
- Snapshots are sequential, not simultaneous chains. More dates increase payload
  size and collection time; unchanged freshness can reject a slow collection.
  Off-hours current requests can remain stale; historical requests are not live
  or executable quotes. The existing regular-session gate is unchanged.

## Staged collection and verification plan

1. Reauthenticate the existing AlphaOS/Public connection; inspect discovered
   SPY/QQQ dates with the existing marketdata scope. Do not change entitlements.
2. Run `python -m scripts.audit_expiration_coverage` in the existing trusted
   environment. It performs the same bounded read-only collection without writes
   and reports observed dates, selected dates, retained strike ranges, discarded
   strike counts, timestamp omissions and chain failures. No raw errors/secrets
   are printed. It is not run against an authenticated provider in this PR.
3. After separately approved deployment, inspect newly collected verified archives
   for each symbol/horizon. Measure collection duration, object size, quote ages
   and request latency before declaring production coverage working.
4. If representative coverage is sound, design a separately reviewed cadence/
   budget for additional monthly/LEAPS dates and a wider strike band. Do not
   indiscriminately expand every heartbeat or reuse stale snapshots across dates.
   Keep Milestone 1 cold/warm production deadline validation separate and open.

## Validation

Final verification:

- Complete Python suite: **990 passed, 64 subtests passed in 340.25 s**.
  Four warnings are the existing baseline SDK constructor deprecations exercised
  by the cold-start transport parity test.
- Dedicated expiration suite: **41 passed in 9.80 s**, including both symbols,
  every horizon, current/historical labels, unavailable dates, stale/checksum
  failures, empty/failed long-dated chains, holiday/weekend boundaries and exact
  REST/OAuth MCP equality. The two new website fixtures are also checked against
  the real collector/reader/service, not handwritten research outputs.
- Website: **89 passed**; typecheck and production build passed.
- Browser: **25 passed in 5.8 s**, including exact monthly/long-dated entry,
  coverage presentation, substitution refusal and missing-expiration recovery.
- Existing website fixture economics/observations compare exactly with baseline
  after removing only the additive coverage metadata. Diff whitespace check passed.

An initial full run exposed two existing fixtures missing the new metadata; these
were updated without changing their research values. A subsequent run crossed a
long wall-clock interruption (pytest reported 60,747.79 s) and failed one legacy
OAuth MCP call with `invalid_token` after login; 989 other tests passed. The final
unchanged complete rerun above passed. No token lifetime or authentication check
was weakened, and the interrupted duration is not a performance measurement.

Primary references inspected:
[Public expiration discovery](https://public.com/api/docs/resources/market-data/get-option-expirations),
[Public exact-date option chains](https://public.com/api/docs/resources/market-data/get-option-chain),
[Public Greek/IV conventions](https://public.com/api/docs/additional-info/greeks),
and the installed Public 0.1.17 adapter. No third-party market data was substituted.
