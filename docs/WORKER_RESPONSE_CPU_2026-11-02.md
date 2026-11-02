# Worker response CPU correction — 2026-11-02

**Release decision: NO-GO on Workers Free.** This is a measured proxy optimization,
not evidence that the complete website fits the 10 ms allowance. Nothing was
uploaded, activated, merged or reconfigured during this work.

## Scope and baseline

- Parent: PR #76, `fix/worker-prefetch-cpu`,
  `737a08240cc8f00cc96ff93163d298bc90f11299`.
- Correction branch: `fix/worker-response-cpu`, stacked on that exact parent.
  The PR head records the correction's exact source SHA.
- Existing candidate: `58c26cb4-9a66-41f2-b25e-c7390659dabf`, unchanged.
- Authentication baseline remains `4e0934712163d543ce740468435ae867d2b77ed8`.
- Read-only Cloudflare verification: three existing versions, no active
  deployments, regular workers.dev endpoint disabled, version previews enabled.
- Target remains `alphaos-web`; no changes to `alphaos`, Render, Supabase,
  credentials, bindings, routes, DNS, observability, timeouts or dependencies.

## Findings, separated by request path

| Path | Evidence | Conclusion |
| --- | --- | --- |
| `POST /api/research/market` | Existing live measurement: 132.062 ms. Authorized read-only historical QQQ response: 4,266,539 decoded bytes, 87 candidates. Route read/parsed the entire body, checked its schema, then serialized/encoded the same tree again with `Response.json`. Local stage and full-route measurements below isolate this redundant work. | Large JSON handling is a demonstrated contributor. It is not established as the entire 132.062 ms. |
| Dashboard and SPY/QQQ navigation | Existing live navigation: 56.453 ms. These pages force dynamic rendering. Compiled local workerd profiles show vinext page dispatch, `buildAppPageElements`, request context, React RSC/SSR and rendering initialization. | Mandatory renders remain after PR #76 removed speculative renders. No evidence supports attributing their CPU to Render requests or bcrypt. |
| Structure Lab | Existing live measurement: 48.087 ms. The page dynamically renders `StructureWorkbench`; initial form has no researched result. Local profiles show RSC/SSR, framework tracing/cache-control parsing and request context, rather than strategy payoff calculations. | Rendering overhead is a separate unresolved problem. Moving financial calculations from this initial render would not address the observed work. |

The Worker wrapper calls the existing session gate before vinext. Session checks
use Web Crypto HMAC; password verification calls Render over authenticated HTTPS.
There is no local bcrypt call in the Worker authentication path. No profile
supports changing session cryptography or bypassing authentication. Framework
tracing and context handling are visible, but samples do not isolate a safe
application-level removal; their configuration was left intact.

The backend capture used an existing authorized local credential without logging
its value. Compressed transfer was 315,536 bytes; headers arrived after about
11.7 seconds and client body completion after about 19.9 seconds. Those are
network/backend/client wall times, **not Worker CPU**. The website's existing
12-second deadline remains unchanged. The real response and raw local captures
remain ignored diagnostic files, excluded from this PR.

## Minimal correction

`web/src/app/api/research/market/route.ts` now reads the complete text and parses
it once. All existing envelope, request, symbol, expiration, width, freshness and
observation validation still runs. Only after successful validation does it wrap
the original JSON text with the same website envelope. This removes the second
large-tree serialization; it does not stream unvalidated data or cache responses.

An iterative numeric-integrity check rejects overflow such as `1e999` before
forwarding. Negative zero, including numeric underflow, uses the old serializer
so the decoded response retains its former normalization. The captured QQQ
response contained 80,940 numbers and no negative zero. Existing error responses,
cancellation, timeout classification and the 12-second limit are unchanged.

The decoded JavaScript response contract and every valid fixture field are
preserved. Transport whitespace, numeric spelling and byte length are not
canonicalized on the fast path. For the measured response the wrapper grew from
4,208,763 to 4,266,613 bytes (about 1.4%); this is the cost of retaining original
formatting instead of serializing again. Payload parsing, encoding, framework
dispatch and full buffering still cost CPU and memory. A negative-zero response
takes the compatibility path and receives no serialization saving.

Changed files are this report, the market route,
`web/tests/market-route.test.mjs` and
`web/tests/workers/runtime-bindings.test.mjs`. No presentation, research-engine,
authentication or Worker configuration files changed.

## Local measurements — not Cloudflare CPU

Windows, Node 22.23.0, actual captured QQQ JSON replayed in memory. No Render or
network wait occurs in the route benchmark. Each implementation is warmed three
times; 20 complete response bodies are consumed. A full decoded-envelope
comparison against the original serializer precedes timing. Process CPU is
batched over 20 operations because Windows per-operation accounting is coarse.

| Route benchmark | Parent | Correction |
| --- | ---: | ---: |
| Median host wall time | 32.477 ms | 21.578 ms |
| Mean host process CPU per operation | 36.650 ms | 27.350 ms |

This run demonstrates **33.6% less local wall time and 25.4% less host process
CPU** for that response. It does not predict a Cloudflare percentile. Independent
stage medians: parse 12.637 ms; parsed-number traversal 3.261 ms; old
`Response.json` construction 17.267 ms; text-response construction 1.200 ms.
Stage results are host wall time; a reported zero from coarse per-stage process
CPU accounting is not evidence of zero CPU.

Native local workerd inspector sampling (1 ms interval, five requests per path,
sequential before/after, same pinned runtime and synthetic session/upstream) gave:

| Path | Parent median wall / active samples | Correction median wall / active samples |
| --- | ---: | ---: |
| Research proxy | 104.313 / 60.801 ms | 96.867 / 43.584 ms |
| Dashboard | 18.399 / 14.218 ms | 18.292 / 15.236 ms |
| SPY navigation | 14.200 / 7.318 ms | 14.828 / 6.443 ms |
| Structure Lab | 14.729 / 5.101 ms | 13.837 / 6.317 ms |

These are diagnostic samples, excluding idle/program/root samples, not billable
CPU. Inspector overhead, cold initialization, GC and host scheduling materially
affect them; other runs varied. They support removing duplicate JSON work, but
do not establish a reliable percentage reduction for workerd or any rendering
improvement. No corrected-version Cloudflare measurement exists.

To reproduce locally: build both revisions with the pinned production-context
vinext toolchain; replay the same authorized response through each route with a
memory-only mocked fetch, consuming the entire response. Compare decoded results
before timing. For native profiling use Miniflare's inspector and V8 Profiler
against each compiled bundle, with synthetic bindings and no external upstream.
Do not log response bodies, passwords, session cookies or service credentials.

## Validation

| Gate | Result and evidence |
| --- | --- |
| Website unit tests | PASS: `npm test`, 206 tests. Includes exact SPY/QQQ fixture parity, Unicode/escaping, no second large serialization, negative zero, overflow rejection, complete-body validation, timeouts and cancellation. |
| TypeScript | PASS: `npm run typecheck`. |
| Production-context build | PASS: `npm run build:vinext`; output targets `alphaos-web`. |
| Artifact/credential checks | PASS: `npm run check:workers`; `node scripts/check-worker-assets.mjs`, 23 public assets scanned. |
| Compiled Workers | PASS: `npm run test:workers`, 16 tests, including new raw-JSON parity/integrity coverage, authentication, CSRF, session handling, runtime-only bindings and isolated native upload preflight. Upload tests block external network access and use only synthetic credentials. |
| Browser | PASS: `ALPHAOS_TEST_WORKERS=true npm run test:e2e -- --workers=1`, 49 tests. Includes desktop/mobile navigation, login/logout, SPY/QQQ, provenance labels and fail-closed errors. Synthetic remote authentication and fixture research, not a corrected live candidate. |
| Prefetch regression | PASS: zero speculative protected RSC renders on desktop/mobile; two intended current dashboard observation requests. Historical fallback remains explicit. |
| Python integration | PASS: 80 tests, 38 dependency deprecation warnings, in a fresh environment installed from `requirements-api.txt` plus pytest/subtests/httpx. Files: `test_website_auth.py`, `test_website_mcp_parity.py`, `test_provenance_entry_integration.py`, `test_research2_api.py`. Initial attempt in an older reused environment stopped at collection because bcrypt was absent; the clean environment resolved that setup issue. |
| CI on correction | Check the focused PR's exact head checks; local results above are not substituted for CI. |
| Corrected live CPU/security/research | UNVERIFIED: upload prohibited in this task. Existing candidate remains unchanged; prior successful research does not validate this correction live. |
| Production isolation | PASS: read-only deployment inventory is empty; no infrastructure writes or candidate uploads performed. |

## Rendering decision and next release gates

The current force-dynamic configuration has demonstrated live requests above
10 ms, independently of this proxy. There is **no evidence that this correction
makes the complete site viable on Free**, and no basis to say all possible
Next.js/vinext configurations are incapable of meeting it.

Two bounded alternatives, neither implemented here:

1. Evaluate vinext's supported build-time prerendering with
   `@vinext/cloudflare/cache/static-assets-adapter` for **data-free UI shells**.
   Keep the existing Worker authentication before every protected HTML/RSC asset,
   leave financial APIs uncached and preserve query-symbol validation. This needs
   explicit private-asset/RSC bypass tests and a bounded proof before selection;
   merely deleting `force-dynamic` is insufficient. `/market` currently consumes
   server search parameters, and the layout renders runtime-dependent controls.
2. Defer the Cloudflare cutover and retain the existing Render website while
   resolving shell rendering. This preserves functionality with existing
   infrastructure; it does not solve Cloudflare CPU or authorize any deployment.

Installed vinext 1.3.1 README documents per-request SSR as its default and the
static-assets adapter/prerender option. Reference:
[Cloudflare production profiling](https://developers.cloudflare.com/workers/observability/profiling-in-production/).

A separately authorized candidate test is justified **to quantify this proxy
change**, not as a production-release attempt. Measure this exact reviewed head
with a representative large QQQ/SPY response and report version-specific CPU
separately for research, initial load, navigation, Structure Lab, login and
logout. Repeat security, provenance and isolation checks. Do not infer CPU from
Render latency, inspector samples or averages across unrelated paths.

Production remains blocked until mandatory rendering and proxy paths have
actual Cloudflare evidence within the account allowance, plus passing live
authentication, CSRF, session, provenance and research gates. If full-response
parsing still exceeds the allowance, choose a separately reviewed bounded
response-contract or hosting change; do not remove validation, truncate results,
cache speculative financial data or silently increase limits.
