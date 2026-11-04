# Cloudflare CPU investigation — November 2, 2026

## Outcome

**A source of unnecessary CPU work is confirmed and corrected locally; the complete cause of the historical live spikes is not yet established. Production remains NO-GO.**

The existing compiled candidate automatically prefetched nine protected page/RSC destinations when the dashboard was opened without navigation clicks. These requests run session verification and vinext rendering. The existing artifact's local CPU samples show materially more work in HTML rendering and first framework dispatch than in a warm health/auth-only path. Removing automatic link prefetch eliminates those nine background requests without removing the two intended SPY/QQQ observation requests.

This does **not** prove that prefetch accounts for every 109.855 ms P95 / 240.395 ms maximum observation. Existing remote analytics lacks a request-path dimension, and the remote profiler returned “No recent executions.” The correction does not establish a 10 ms per-request budget: explicitly requested dynamic renders remain expensive locally. Do not upload or activate based on this report.

## Exact source, isolation and artifact preservation

- Investigated live Worker: `alphaos-web`.
- Existing version: `7439ba96-9e88-4302-953f-d2a6e70b8682`.
- Baseline/runtime source: `4e0934712163d543ce740468435ae867d2b77ed8`.
- Original compiled entry SHA-256 remains `6a852591a21fc0298482811cd9525ce21701e224cd636c6406bbb21ec3f30c78`.
- Isolated correction branch: **`fix/worker-prefetch-cpu`**, based directly on that SHA.
- Isolated checkout: `C:\Users\rober\OneDrive\Documents\Alpha OS\worker-cpu-prefetch`.
- No changes from the original checkout's pre-existing dirty Sprint 1 files were incorporated. No PR #75 or pilot changes were made.

The original artifact was inspected/profiled **before** any build. Only the isolated correction was subsequently built locally for verification. Nothing was pushed, uploaded, deployed, merged or activated. No credentials, settings, logging, plans or routes were modified. This branch has not run new GitHub CI.

## Confirmed findings

### 1. Bcrypt is absent from the Worker

Source `web/src/lib/website-auth.ts` calls the fixed HTTPS `/v1/website-auth/verify` endpoint with server-only bindings. The compiled artifact contains that call and no bcrypt implementation markers. Local password-setup/test tooling retains bcrypt; that does not make it part of the deployed Worker entrypoint.

This differs from the older candidate `3883bf31…`, whose isolated incorrect-password verification consumed 369.586 ms at the edge. There is no evidence that the current spikes are caused by in-Worker bcrypt.

### 2. Cryptography and middleware review

- Sessions use HMAC-SHA256 through Web Crypto, not a password KDF. The bcrypt hash is included as key material, not evaluated by the Worker.
- `key()` imports a non-extractable HMAC key for each sign/verify operation. That is repeated work, but measurements do not justify calling it the main live hotspot or weakening/changing session validation.
- `validSession` performs bounded token parsing, one HMAC verification, expiry/audience checks and configuration validation. Protected requests verify once. Login without a cookie performs no HMAC verification and signs only after successful backend acknowledgement.
- Password body reads are bounded at 2,048 bytes; verifier acknowledgement at 128 bytes. No local bcrypt fallback or backend retry loop exists.
- No CryptoKey cache, auth bypass, reduced hash cost, different cookie, altered session expiry or changed limiter was introduced. Optimizing cryptography speculatively would not be a supported explanation for the rendering evidence.

### 3. Dynamic rendering and initialization cost

The existing artifact was loaded directly in local workerd/Miniflare using public synthetic test credentials and a stubbed backend. No rebuild or production cookie was required. CPU-only DevTools samples were collected and mapped using existing source maps.

Representative mapped frames include vinext `app-rsc-handler.js`, `app-page-route-wiring.js` (`buildAppPageElements`), `app-page-dispatch.js`, request-context/pipeline functions, and React's production RSC/SSR implementation. These are production framework modules, not evidence of a development React build.

Cold/first API dispatch and first HTML render are more expensive than subsequent dispatch. Since these local page renders did not wait on a real Render backend, their work cannot be explained by Render bcrypt latency or network waiting alone. The measurements are local samples, not Cloudflare billing measurements.

### 4. Automatic prefetch amplifies that rendering work

An authenticated local browser opening the unchanged `/dashboard` emitted these background RSC requests without a navigation click:

```text
/journal
/session
/strategies
/market
/market?symbol=QQQ
/settings
/risk
/structures
/market?symbol=SPY
```

The diagnostic recorded pathname and whether `_rsc` was present, not cookies or secret headers; the three `/market` entries arise from separate navigation destinations. Exact ordering is not important. Two `/api/research/market` calls were also present and are intended dashboard behavior.

`next/link` defaults allowed viewport/idle/hover prefetch. Private pages and RSC responses still pass the authentication guard; the performance issue is unnecessary authenticated rendering, not anonymous data exposure. The new desktop and mobile regression fails on the original compiled artifact and passes on the correction.

## Small correction

Set `prefetch={false}` on the existing seven Link expressions across five files:

1. `web/src/components/shell/Sidebar.tsx`
2. `web/src/app/dashboard/page.tsx`
3. `web/src/components/dashboard/DashboardResearch.tsx`
4. `web/src/components/market/MarketResearchPanel.tsx`
5. `web/src/components/market/MarketUnavailable.tsx`

Explicit navigation still uses the existing Link/router behavior and requests the chosen destination when clicked. URLs, symbols, layout, labels, CSS, research refresh, HTTP evidence handling and authentication are unchanged. No caching of protected content was introduced.

The tradeoff is deliberate: a destination is fetched on navigation instead of speculatively beforehand. This reduces avoidable requests; it is not a replacement rendering architecture or a solution for the remaining per-request SSR cost.

## Before/after local measurements

| Local dashboard behavior | Existing artifact | Corrected local build |
|---|---:|---:|
| Background protected-page RSC requests after hydration | **9** | **0** |
| Intended dashboard research/observation calls | **2** | **2** |
| Sign Out present in synthetic local desktop harness | yes | yes |
| New desktop/mobile no-background-prefetch regressions | **2 failed** | **2 passed** |

The owner's previously reported missing Sign Out control on the live candidate is not reproduced by this local result and is not claimed fixed.

The following instrumented local wall times are descriptive samples (one process per artifact, three requests per route; warm median uses iterations 2–3). **They are not Worker CPU allowance measurements or statistically established latency improvements.**

| Explicit request | First wall ms before / after | Warm median wall ms before / after |
|---|---:|---:|
| /login | 29.61 / 18.77 | 6.09 / 4.87 |
| /api/health | 21.62 / 20.97 | 6.60 / 6.44 |
| /dashboard | 69.03 / 67.12 | 23.34 / 23.44 |
| /market | 25.59 / 27.13 | 18.55 / 17.03 |
| /structures | 21.92 / 20.14 | 17.67 / 16.56 |

The sampled-active estimate for the first dashboard render was approximately 63.1 ms before / 61.1 ms after. It remains large. Whole-browser sampling varied significantly with cold/warm state and inspector overhead, and is **not used as proof of CPU savings**. The robust measured improvement is nine fewer speculative requests, not a claimed per-request CPU reduction.

## Remote telemetry and limits

The existing version's prior exact-version analytics remains valid evidence: max 240.395 ms; success-bucket P95 109.855 ms; no request-path dimension. The prior correlated incorrect-login bucket was 2.707 ms and anonymous buckets approximately 0.806–3.016 ms. These low-cost probes do not explain or excuse larger page/request spikes.

A CPU-only capture was attempted using the documented endpoint for the exact version. It returned HTTP 404 / code 10393, **“No recent executions were found for this Worker.”** After one bounded candidate `/login` request (HTTP 200, no cookie), a capture using the canonical Worker ID returned the same message. No feature/settings were enabled. This is a capture limitation; it is not proof that the account plan is unsupported.

The available browser tooling does not expose the owner's authenticated browser. Production cookies were not exported or manufactured using signing secrets. Consequently, the historical live path attribution and a controlled live authenticated page/research capture remain **UNVERIFIED**. The local path reproduction must not be relabeled as a live path-level trace.

Two bounded direct Render research reads during this investigation timed out from the diagnostic client. No response was substituted and no market data was fabricated. That client wall-time observation is not evidence that network waiting consumes Worker CPU, nor a diagnosis that the Render service is down.

## Regression and security validation

- **49 browser tests passed** against the corrected compiled Worker, including desktop/mobile navigation, symbol selection, authentication/session/logout, anonymous rejection, CSRF, structure economics, SPY/QQQ provenance and fail-closed behavior. Tests used one browser worker to avoid the already-known unrelated shared-file test-harness race in the baseline branch.
- **202 website unit tests passed.**
- **15 compiled Worker/native synthetic preflight tests passed.** All native upload simulations used the existing offline/loopback protections; no Cloudflare upload occurred.
- **12 Python authentication tests passed.** Backend code is unchanged.
- Typecheck and local production-context build passed.
- Worker-output check passed; **23 public assets** passed credential-reference scan.
- `git diff --check` passed.

The new `web/tests/browser/no-background-prefetch.spec.ts` verifies no speculative RSC on hydration/viewport/hover and successful deliberate navigation to Structure Lab on desktop/mobile. It fails against the unchanged candidate artifact, so it is not merely a source-text assertion.

## Remaining live-validation requirements

1. Keep the current candidate undeployed. **No CPU compliance claim is made for this local correction.**
2. Review the isolated change and its tests. Any future upload needs separate approval and exactly identified source/version.
3. To establish the complete live cause, arrange an accessible owner-authenticated candidate session and coordinated per-path windows, or obtain an approved CPU-profile/path-diagnostic plan that works for version URLs. Never collect password/body/cookie/Authorization values. A logging/tracing configuration change requires separate approval.
4. Measure first and warm HTML, RSC, login, logout and SPY/QQQ API requests separately on Cloudflare; include maximum/P95/P99, request counts, initialization state and invocation outcomes. Distinguish Render waiting from local execution.
5. Confirm the corrected version has no speculative page requests in the real browser. Then measure its actual per-request CPU. Lower request volume alone is not a 10 ms allowance pass.
6. If explicit rendering still exceeds the allowance, inspect the measured framework/rendering path before selecting another minimal correction. Do not remove provenance checks, disable auth, cache private responses indiscriminately, upgrade plans or redesign the site to declare success.
7. Retain the separate existing logout/persistence and release gates. No production activation or merge is authorized by this report.

References: [Cloudflare production profiling](https://developers.cloudflare.com/workers/observability/profiling-in-production/), [Workers metrics](https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-workers-metrics/). Local raw evidence and diagnostic scripts are retained under this worktree's ignored `diagnostics/` directory, including baseline/corrected request traces, mapped samples and test logs; no production credential values are included.
