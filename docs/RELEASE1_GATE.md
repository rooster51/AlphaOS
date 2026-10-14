# Release 1 dependency review and acceptance gates

Review date: 2026-10-14. Scope: existing PR #40 only; no deployment or configuration changes.
Reviewed head: `da3adb0794b0426ea8c4b5db14b039c28cf53047`.
Main: `7f7ef53c85151711ef5fdc3c5d092a7a3e6d84cb`.

## Verified checks

[CI run 38507746724](https://github.com/rooster51/AlphaOS/actions/runs/38507746724) passed on the reviewed head: backend 760 tests and 40 subtests; website 38 tests; browser 9 tests; TypeScript and production build passed. These results are fixture/contract evidence, not live provider verification. Local documentation edits have not been pushed and are not covered by a new CI run.

`npm audit --package-lock-only --json`: exit 1, seven affected packages (five high, two moderate, zero critical). This expected audit exit indicates findings, not a test failure.
`npm audit --package-lock-only --omit=dev --json`: exit 0, zero reported production dependency vulnerabilities.
Both audits query the exact lockfile without installing or changing dependencies. Counts reflect the advisory database at review time, not proof of absence of all vulnerabilities.

## Seven findings, two underlying advisories

Every listed package has `dev: true` in web/package-lock.json. Tailwind is a direct devDependency; the other packages are transitive build/watch tooling. They are not direct production dependencies. Development dependencies can still be installed on a deployment host; this audit does not claim they were pruned there.

| Package | Locked version | Severity | Dependency path / cause |
|---|---|---|---|
| braces | 3.0.3 | High | Tailwind -> chokidar or micromatch -> braces; recursive pattern stack exhaustion |
| chokidar | 3.6.0 | High | Tailwind watcher; inherited braces finding |
| micromatch | 4.0.8 | High | Tailwind matcher -> braces; inherited finding |
| fast-glob | 3.3.3 | High | Tailwind -> fast-glob -> micromatch -> braces; inherited finding |
| tailwindcss | 3.4.19 | High | Direct build dependency; aggregates the affected dependency chains |
| postcss-selector-parser | 6.1.4 | Moderate | Tailwind directly and through postcss-nested; quadratic selector parsing |
| postcss-nested | 6.2.0 | Moderate | Tailwind -> postcss-nested -> selector parser; inherited finding |

Sources: [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), [selector-parser advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf).

### Exposure and safe disposition

Source inspection: web/tailwind.config.ts uses fixed repository-local content globs; web/postcss.config.js loads Tailwind/autoprefixer during CSS compilation. web/src contains no imports of the affected parsers/watchers and no route accepting CSS or glob patterns for compilation. Research inputs are not passed to these tools. package.json starts the built app with `next start`, separately from `next dev` and `next build`.

Therefore no remotely supplied research-request path to either vulnerable parser was identified. Residual exposure is build/development availability when processing malicious repository CSS, selectors or glob configuration. Trusted, reviewed source and a production server that does not compile untrusted inputs are the assumptions behind this assessment. No exploit test or deployed filesystem inspection was performed. Do not equate dev-only labeling or a clean omit-dev audit with zero build risk.

The braces advisory currently lists no patched version. The selector-parser fix starts at 7.1.6, outside Tailwind 3/postcss-nested 6's declared 6.x ranges. An override would cross that compatibility boundary and would not resolve braces. npm proposes Tailwind 4.3.3, a breaking migration explicitly excluded from this milestone. No verified compatible all-findings remediation is available from this review.

Disposition: the owner accepted the documented build-time dependency risk for controlled staging in the documentation-publication instruction. Retain the tested lockfile; the seven findings remain unresolved, not fixed. This bounded acceptance assumes trusted, reviewed build inputs and no runtime compilation of untrusted CSS or glob patterns. It does not authorize a push, merge, staging deployment or production release. Review again before release or when compatible upstream fixes appear. A future compatible patch must pass install, audit, typecheck, unit, build and browser checks. Do not run audit fix --force, force a parser major override, or remove development dependencies before the CSS build. No dependency or application-code change is necessary for this disposition. Reassess the exception if dependency versions, build inputs or runtime exposure change, and before production approval.

## Remaining acceptance gates

1. **Dependency disposition — accepted for controlled staging only:** retain the bounded exception above; reassess before production approval. Current Next.js is 16.4.0; the old Next 14 critical finding is superseded, not an active finding on this head.
2. **Pinned release review:** refresh PR #40's outdated description after approval to publish these local documentation changes; verify head and final CI before any merge. No merge or push is authorized by this document.
3. **Authorized staging configuration/version check:** verify canonical PUBLIC_API_SECRET and PUBLIC_ACCOUNT_NUMBER, archive credentials, demo mode disabled, and exact API/website revisions without exposing values. The earlier wrong-case key, timeout and archive failures are historical observations, not a new configuration inspection. Do not assume they remain present or have been fixed.
4. **Real SPY/QQQ data:** on a separately approved staged revision, verify complete daily OHLC and coverage, checksum-validated archive bytes, identity, supported expirations, observation/collection/slot times, freshness and session boundaries. Record exact requests and safe diagnostics. No fallback prices, relaxed freshness or fabricated candidates.
5. **Research acceptance:** validate QQQ and SPY with actual archived expirations; include QQQ capital 20/170/300 and SPY 150 with supported widths. Record generated, rejected and accepted counts plus classification, routing, maximum loss and rejection reasons. Zero candidates can pass when explained by valid evidence; archive/history failure is not a successful research result.
6. **Website/REST/MCP parity:** compare equivalent inputs on the same approved backend revision and evidence snapshot (or explicitly account for changing timestamps). Confirm the 17 tools, research-only status, provenance, historical economics and missing-evidence reasons. Browser display remains limited; symbol-only defaults are not equivalent to explicit capital/width/expiration requests. Unsupported intraday/early-exit EV must stay null.
7. **Production approval:** only after documented staging acceptance, seek separate approval for an exact production SHA and rollback plan. No journal, migration, collector activation or secrets changes are included.

Release decision: functionally CI-green on the reviewed code SHA; build-time dependency risk accepted for controlled staging, not remediated; real staging verification remains pending and production readiness is not established. This document does not certify current deployed services or launch readiness.
