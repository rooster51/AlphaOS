# Release 2.0 reproducible test and evidence matrix

Date: 2026-10-19, America/New_York. Source baseline:
`aade8038132014e940b5dabce9ce23b46becc786`.
Read [the readiness findings](RELEASE2_READINESS_AUDIT.md) before interpreting
results. This is an audit, not a backtest, deployment certification or strategy
recommendation. No application/test code or dependency was changed.

## Labels and conditions

**C / CODE VERIFIED:** source or runtime-contract inspection.
**F / FIXTURE VERIFIED:** executed deterministic offline test/fixture case.
**L / LIVE VERIFIED:** a request/control-plane observation actually executed here.
**NV / NOT VERIFIED:** missing data, failed request or unexecuted combination.
**Z:** L successful research response with zero candidates; not strategy readiness.
**X:** live request failed (HTTP 502); underlying research outcome NV.

All Python tests used the existing Python 3.12.14 development environment; no
fresh dependency resolution. Website used existing node_modules, Node 24.20.0;
CI Node 22 was not independently exercised. Supabase installed 2.31.0 versus
collector-manifest pin 2.32.0; isolated collector install NV. No secret file,
credential value or database was opened for live verification. Test fixtures use
fake storage/providers and fixture-only auth values, not production tokens.

Local raw/sanitized probe captures are in ignored `diagnostics/release2-*` files.
They are not required deployed dependencies or committed market-data fixtures.
Only the two audit Markdown files are published. Future live requests need not
return the same snapshot/prices; baseline tests are reproducible, live conditions
are repeatable but time-varying. This report contains summarized evidence.

## Executed existing validation

Run from repository root with existing dependencies. This host used
`../phase6-worktree/.venv/Scripts/python.exe`; a different checkout may use its own
Python 3.12 environment. Use a new temporary directory for repeated full runs.

```powershell
$env:PYTHONPATH="$PWD;$PWD/tests"
& ../phase6-worktree/.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp='../release2-audit-python-temp'
```

| Command, under `web/` unless Python | Actual outcome |
|---|---|
| Full Python command above | **892 passed, 64 subtests passed in 465.85s** |
| `npm run typecheck` | Passed, exit 0 |
| `npm test` | **61 passed, 0 failed, 0 skipped** |
| `npm run build` | Passed; Next.js production routes generated |
| `npm run test:e2e -- --workers=2` | **15 passed in 23.3s** |

No failing check was bypassed and no test weakened. React 18 deprecation,
module-type and browser NO_COLOR/FORCE_COLOR warnings remain. These checks are F,
not evidence that all supported strategies have live quotes or historical EV.
No new dependency audit or isolated installation was performed.

Existing test groups, all included in that full run:

| Evidence area | Source tests / relevant condition |
|---|---|
| Archive read/write integrity | `test_archive_read_path.py`, `test_daily_quant.py`, `test_intraday_execution.py`, related daily/intraday tests: missing/corrupt/checksum/context/future availability, partial data, immutable recovery, slot gates using fakes |
| Current/historical, weekends/holidays | `test_research2_api.py`, `test_run_market.py`, archive/session tests: explicit mode, stale rejection, original-time economics, early close and expiration availability |
| Classification/routes/zeros | `test_opportunity_classifier.py`, `test_opportunity_router.py`, `test_opportunity_session.py`, `test_candidate_generation_diagnostics.py`: unknowns, supplied states, route/constructor stages, bad quotes/delta, positive controlled fixtures |
| Longs/structures/payoff | `test_long_option_research.py`, `test_long_option_discovery.py`, `test_structure_research.py`, `test_options_payoff.py`: signed quantities, cashflow signs, exact roots/risks and malformed geometry |
| Historical evidence | `test_historical_economics.py`, `test_trusted_historical_adapter.py`, `test_structure_economics_integration.py`, `test_historical_analogs.py`: matched/matured outcomes, sample/horizon/provenance gates, honest unavailable intraday/early exit |
| Contracts/auth/parity | `test_mcp_api.py`, `test_research2_api.py`, `test_website_mcp_parity.py`, `test_legacy_explicit_contracts.py`, `test_architecture_consolidation.py`: OAuth consent/scopes, REST auth, sanitizer, 19 operations/17 tools, fixture envelope equality |
| Website/browser | Existing 61 website tests and 15 Playwright cases: editable capital, mode, expiration, exclusions, diagnostics, historical labels, known errors, invalid controls, desktop/mobile navigation, legacy `/strategies` compatibility |

These filenames identify scopes, not a claim that every possible combination in
the rest of this document is parametrized by those tests.

## Additional offline explicit-structure and capital probe

**F:** reused the exact 11 existing payoff cases in
`tests/test_historical_economics.py::test_all_families_use_existing_payoff`,
changed only the underlying identity to SPY or QQQ, and called the actual REST
structure route. The source scenario is spot 100, as_of 2026-10-09,
expiration 2026-10-16, $1 total fee. This does not assert a real SPY/QQQ price or
provider-listed monthly contract. Deliberately missing fake storage must leave
historical evidence unavailable. No live provider/storage request is permitted.

The executed probe can be reproduced with this Python body in a separate process
(with repository/tests on PYTHONPATH):

```python
import importlib, os
from fastapi.testclient import TestClient
from alphaos_api.research2 import ArchiveResearchService
from modules.historical_economics import evaluate_historical_economics
from modules.supabase_archive import ArchiveUnavailable

api = importlib.import_module('alphaos_api.app')
fixtures = importlib.import_module('tests.test_historical_economics')
def unavailable(*args, **kwargs):
    raise ArchiveUnavailable('Audit fixture: deliberately absent storage')
api.app.state.archive_research = ArchiveResearchService(
    read_snapshot=unavailable, history_loader=lambda _: None)
os.environ['ALPHAOS_API_TOKEN'] = 'audit-fixture-token'  # local process only
client = TestClient(api.app)
cases = fixtures.test_all_families_use_existing_payoff.pytestmark[0].args[1]
for symbol in ('SPY', 'QQQ'):
    for legs, credit, _ in cases:
        trade = fixtures.trade(legs, credit)
        trade['symbol'] = symbol
        body = {k: trade[k] for k in ('symbol','expiration','spot','credit','fees','legs')}
        body['as_of'] = fixtures.AS_OF
        response = client.post('/v1/research/structure', json=body,
            headers={'Authorization':'Bearer audit-fixture-token'})
        assert response.status_code == 200, response.text
        result = response.json()['research']
        assert result['historical_economics']['historical_evidence_status'] == 'unavailable'
        for capital in (150, 300, 500, 1000):
            outcome = evaluate_historical_economics(trade, as_of=fixtures.AS_OF,
                available_capital=capital)
            assert (outcome['capital_eligibility']['status'] == 'ineligible') == (
                result['capital_at_risk'] > capital)
```

Result: **22/22 REST cases returned 200; 88/88 capital comparisons matched**.
The code above intentionally uses existing version-pinned test parametrization;
if test layout changes, locate the same fixture cases rather than inventing quotes.
Maximum-loss outcomes are in the audit's small-account table ($101/$201/$301/$401).
At $300, a $301 credit-spread example remains ineligible: fee boundaries matter.
The same fixture exercise proves neither liquidity nor broker margin.

## Live request ledger

All times below UTC; subtract four hours for audit-date EDT.

| Probe | Actual observation / limitation |
|---|---|
| Initial website current/historical, SPY/QQQ, $1,000, omitted expiration | Four HTTP **502** responses, `backend_service_unavailable`, 16:00:56–16:00:57. No research accepted. |
| Public backend `/health` | HTTP **200**, read_only true, authentication configured true. No token value read. |
| Public backend `/openapi.json` | HTTP **200**, **19 paths**, live path declarations equal local `app.openapi()['paths']`. This is schema reachability, not a private research call. |
| Connected MCP `run_market`, SPY/QQQ, $1,000 | Two attempts failed with connector `UNAUTHORIZED`, “requires reauthentication.” No backend HTTP/research result; live OAuth parity NV. Declared arguments omit `research_mode`, unlike repository source. |
| Bounded follow-up website current/historical, both symbols, $1,000 | Four HTTP **200**, 16:02:47–16:03:03. Same observation per symbol across modes; current max age 600, historical null. SPY 2 debit hypotheses / QQQ 0. |
| Expiration x budget live matrix below | **48** current-mode requests, completion times 16:04:11–16:07:44; **44 HTTP 200, four HTTP 502**. No failed matrix cell retried to make it pass. |
| Render metadata | Read-only list_services/list_deploys in previously authorized workspace: API and website `live` at aade8038..., manual deploy, auto-deploy off; retained API staging live at 15dc5683... |

The four initial 502s plus four matrix 502s are all reported. A later successful
request does not erase them. Exact upstream cause/cold-start/resource explanation
NV. The completed live matrix is an audit sample, not a measured production SLA.
No direct authenticated REST token was read; the website's configured server-side
bridge performed backend authentication. No private archive objects were downloaded
independently, no database writes made, and no live MCP result obtained.

Example public read-only reproduction (do not place credentials in the body):

```powershell
Invoke-WebRequest 'https://alphaos.onrender.com/health' -SkipHttpErrorCheck
Invoke-WebRequest 'https://alphaos.onrender.com/openapi.json' -SkipHttpErrorCheck
$body = @{symbol='SPY';research_mode='current';available_capital=1000} | ConvertTo-Json
Invoke-WebRequest 'https://alphaos-web-staging.onrender.com/api/research/market' `
  -Method Post -ContentType 'application/json' -Body $body -SkipHttpErrorCheck -TimeoutSec 45
```

First request with omitted expiration discovers the available list. For this audit,
that actual list was Oct 19,20,21,22,23,26. The matrix explicitly submitted those
six returned dates and capital 150/300/500/1000 for each symbol, default width 5,
current mode, two concurrent requests maximum. Reproduction should discover the
new current list rather than claiming these dates are still current or available.
Historical mode always uses the latest archive; it cannot recover this exact
snapshot after a newer one appears. Raw observation/quote payloads were not
converted into fabricated committed fixtures.

## Actual live SPY/QQQ expiration x capital matrix

Numbers are **returned capital-accepted structure counts**, not evidence-qualified
opportunities. All successful SPY requests generated two unclassified call/put
debit hypotheses. `0C` means both exceeded capital; `0R` means no supported
construction family was reached, not a quote-quality or capital rejection.
`X` is HTTP 502 and therefore NV for the requested research cell.

| Symbol | Returned expiration | Calendar DTE | $150 | $300 | $500 | $1,000 |
|---|---|---:|---|---|---|---|
| SPY | 2026-10-19 | 0 | X | X | 2 | 2 |
| SPY | 2026-10-20 | 1 | 1 | 2 | X | 2 |
| SPY | 2026-10-21 | 2 | 0C | 2 | 2 | 2 |
| SPY | 2026-10-22 | 3 | 0C | 2 | 2 | 2 |
| SPY | 2026-10-23 | 4 | 0C | 2 | 2 | X |
| SPY | 2026-10-26 | 7 | 0C | 2 | 2 | 2 |
| QQQ | 2026-10-19 | 0 | 0R | 0R | 0R | 0R |
| QQQ | 2026-10-20 | 1 | 0R | 0R | 0R | 0R |
| QQQ | 2026-10-21 | 2 | 0R | 0R | 0R | 0R |
| QQQ | 2026-10-22 | 3 | 0R | 0R | 0R | 0R |
| QQQ | 2026-10-23 | 4 | 0R | 0R | 0R | 0R |
| QQQ | 2026-10-26 | 7 | 0R | 0R | 0R | 0R |

SPY used one archive checksum across all successful matrix requests. Returned
call/put max losses by expiration were $90/$105, $184/$146, $216/$156, $236/$160,
$251/$162 and $258/$164 respectively. At Oct 20/$150 only the put debit passed;
Oct 21–26/$150 report `all_structures_exceed_capital`. These are dated research
cashflows with constructor assumptions, not executable fills or current prices.
The 0DTE $150/$300 cells remain NV despite apparent affordability in other cells;
we did not overwrite failed requests with inferred outcomes.

QQQ used two successive archive checksums; all 24 requests returned no candidates.
Direction unknown, movement breakout, premium/volatility unknown produced
`long_option`, `directional_debit_spread`, `directional_bwb`; `_families` needs known
direction for these generic routes. Routing output was zero supported families;
construction, economics and capital were `not_attempted`, yet the aggregate reason
was `no_constructible_structure`. No claim is made that QQQ cannot support any
valid strategy. That would require constructing against the actual evidence under
a separately reviewed policy, not inventing direction during an audit.

First successful observations: SPY 12:01:50.187214 EDT / QQQ 12:01:54.414243 EDT.
Metadata received counts were 1,828 / 2,282; retained bucket counts 924 / 820 and
selected 0DTE clean call/put counts 77/77 and 61/61 respectively. These are different
count scopes, not proof of a checksum mismatch. Successful matrix collection ages
ranged **7.37–251.79 seconds**, below the current 600 ceiling. Sampled returned SPY
candidate legs (62 repeated leg appearances) had bid/ask timestamps and OI fields;
that does not verify OI date, venue, depth, acceptable spreads or fills. Every
returned candidate's historical evidence status was `unavailable`.

## Strict expiration-by-strategy verification grid

This grid concerns **end-to-end discovery in the live archive pathway**. Codes
intentionally do not convert general payoff tests into live coverage. `L*` means
some successful capital cells produced the family; failed cells remain NV as above.
`Z` means L zero due to the routing condition, not that the strategy is invalid.
`NV/U` means unavailable canonical strategy pathway in code, not an executed trade.

| Symbol / family | 0DTE | 1DTE | 2–7 DTE (2/3/4/7 observed) | 8–45 DTE | Monthly | LEAPS |
|---|---|---|---|---|---|---|
| SPY call debit | L* | L* | L* | NV | NV | NV |
| SPY put debit | L* | L* | L* | NV | NV | NV |
| QQQ call debit | Z | Z | Z | NV | NV | NV |
| QQQ put debit | Z | Z | Z | NV | NV | NV |
| SPY long call / long put | NV | NV | NV | NV | NV | NV |
| QQQ long call / long put | NV | NV | NV | NV | NV | NV |
| SPY put credit / call credit | NV | NV | NV | NV | NV | NV |
| QQQ put credit / call credit | NV | NV | NV | NV | NV | NV |
| SPY symmetric long butterfly | NV/U automatic | NV/U | NV/U | NV | NV | NV |
| QQQ symmetric long butterfly | NV/U automatic | NV/U | NV/U | NV | NV | NV |
| SPY iron butterfly / both BWB orientations / condor | NV | NV | NV | NV | NV | NV |
| QQQ iron butterfly / both BWB orientations / condor | NV | NV | NV | NV | NV | NV |
| SPY/QQQ calendars / diagonals | NV/U | NV/U | NV/U | NV/U | NV/U | NV/U |
| SPY/QQQ long straddles / strangles | NV/U | NV/U | NV/U | NV/U | NV/U | NV/U |
| SPY/QQQ legacy catalog-only structures | NV/U canonical | NV/U | NV/U | NV | NV | NV |

A missing family in this one market state is not a negative execution test of its
constructor. Conversely, F constructor tests do not turn these NV cells into L.
No weekly/monthly/LEAPS provider listing outside the returned archive was fetched.
A third-Friday date in a fixture is not a live monthly option chain.

## Offline expiration fixtures and remaining holes

| Bucket | Existing deterministic fixture evidence executed in full suite | Honest limit |
|---|---|---|
| 0DTE | `test_run_market` and `test_research2_api`: QQQ/SPY archive fixture 2030-01-02, late-session routing and capital/REST/OAuth parity; collector and session fakes | F controlled archive/quote behavior, not all-strategy real-time 0DTE outcomes |
| 1DTE | `test_structure_research` and `test_long_option_research`: QQQ explicit as_of 2030-01-17 -> 2030-01-18; both long option types, debit/credit/butterfly/BWB/condor payoff cases where parametrized | F explicit scenarios; not an all-family SPY+QQQ discovery grid |
| 2–7 DTE | `test_candidate_generation_diagnostics`: SPY/QQQ 2026-10-16 -> 2026-10-19, unknown/routed debit fixtures, zeros and capital; extra audit probe both symbols 2026-10-09 -> 2026-10-16 explicit supported families | F examples only; daily outcome horizons are sessions, not calendar DTE |
| 8–45 DTE | `test_opportunity_session`: supplied/shared-position examples as_of 2030-01-01 -> 2030-01-31; preexisting `demo_chain(30)` constructor fixtures explicitly synthesize test quotes | F selected internal/payoff/constructor examples, not canonical collected 30-day evidence, not actual listing verification |
| Monthly | 2026-10-16 existing same-expiry payoff/scenario fixtures; completed-session integration has its own trusted fake archive/history | F dated math/evidence gates only; live monthly chain and broad monthly horizon NV |
| LEAPS | Existing evaluator accepts `holding_period='leaps'` and refuses unsupported early-exit economics | A label/refusal test is not long-dated quote/EV evidence: full LEAPS pathway NV |

No new expirations, option chains, classifications or historical outcomes were
manufactured for this audit. Additional offline probes only reused existing
fixtures with an explicit SPY/QQQ identity for math/contract testing.

## Read-only operations reproduction and limitations

Render read-only tools used: `list_services` in the previously confirmed workspace,
then `list_deploys(limit=1)` for `srv-daqillmgekts73ak0mj0` (API),
`srv-db6iok3rjlhs73eveqs0` (website), `srv-db6mql2d0e5s73atk5e0` (retained staging).
No settings/env-value/log/database mutation or deploy tool was called.
Deployment semantics were checked using the Render monitoring skill and current
[deploy documentation](https://render.com/docs/deploys) /
[health documentation](https://render.com/docs/health-checks). Markdown-reference
fetches were unreadable by the web tool; the HTML references were read instead.

Unexecuted / NV: isolated package installs and resolver checks, actual CI Node 22,
live MCP reauthentication and schema refresh, direct private REST auth request,
private object checksum re-download, scheduler configuration/token expiry and
continuous slot coverage, alert delivery, after-close/weekend live modes, live
monthly/LEAPS/mixed-expiry research, historical option fills or intraday EV,
calibrated POP and broker-account/buying-power integration.

## Publication guard

Only `docs/RELEASE2_READINESS_AUDIT.md` and this file may be committed in this audit.
Verify `git diff --cached --name-only` and `git diff --cached --check`, commit on
`codex/release2-readiness-audit`, push with Git and verify remote SHA. No merge,
deploy, dependency upgrade, branch deletion or implementation milestone follows
from publishing these findings.
