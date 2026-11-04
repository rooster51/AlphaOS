# Workers Free authentication replacement — local preparation only

The uploaded candidate `3883bf31-f177-4e90-96f3-ea8e37a38f40` remains unchanged
and undeployed. Its isolated incorrect-password request consumed 369.586 ms CPU,
above the owner-confirmed Workers Free 10 ms allowance. A completed login without
an `exceededCpu` outcome does not prove CPU compliance.

## Narrow architecture change

The login form, cookie signing algorithm, 30-day expiry, origin-bound sessions,
logout, CSRF checks and native 5-attempt/60-second Cloudflare limiter are unchanged.
There is no bcrypt implementation in the replacement Worker entrypoint. The
existing local password-setup script still uses bcryptjs to create cost-12 hashes.

After CSRF/input/rate-limit validation the Worker sends one HTTPS POST to the
fixed `/v1/website-auth/verify` path on `ALPHAOS_API_URL`. It authenticates using
the existing server-side `ALPHAOS_API_TOKEN`. The JSON body contains the submitted
password and existing `ALPHAOS_PASSWORD_HASH`. Both are sensitive: never log the
body, headers, request/exception representations, or capture them in telemetry.
No credentials are returned to the browser. Redirects are not followed. A 12-second
deadline covers the request and bounded response consumption; no retry or local
bcrypt fallback is performed.

This is a trusted service-to-service verification operation, not a public login
endpoint. Render authenticates the bearer token before reading credentials or
performing bcrypt. The supplied hash comes from the trusted Worker, so Render
needs no additional secret or database. An existing API-token holder is trusted
to invoke this helper; it does not create a browser session or expose the Worker
signing key. Existing research and MCP token permissions are unchanged.

Render accepts only cost-12 bcrypt hashes, 1–72 UTF-8 password bytes and a bounded
2048-byte JSON body with exactly two unique fields. Native `bcrypt==5.0.0` runs in
the thread pool, with at most two active verifications per process. Excess work
fails closed with 503; there is no unbounded bcrypt queue. The endpoint returns
only `{"verified":true}` or `{"verified":false}`, with `Cache-Control: no-store`.
The Worker issues a cookie only for a strict, bounded HTTP 200 boolean response.
Wrong passwords return 401; redirects, malformed responses, outages, saturation,
authentication failures and deadlines return a generic 503 without a cookie.

## Approval-gated release order

1. Review the focused source/test changes. Do not push blindly: PR #67 has an
   automatic Preview integration, and this run authorizes no remote upload.
2. Obtain explicit approval to release the Render endpoint and install the pinned
   bcrypt dependency. Keep existing Render credentials, services and plans intact.
   Verify its bearer boundary with synthetic credentials first; no production
   request bodies may be logged. Existing research endpoints must remain healthy.
3. Only after approval, upload a replacement undeployed `alphaos-web` version
   following `CLOUDFLARE_VERSION_UPLOAD.md`, using the existing four runtime secrets.
   Do not reuse the old SHA tag or deploy version `3883bf31` as the fix.
4. Verify the new exact version, zero production deployments and unchanged Preview
   and `alphaos`. Complete owner login, restart persistence, logout, authenticated
   CSRF, SPY/QQQ research, provenance/freshness and non-executable archive labels.
5. Measure version-specific CPU in microseconds, converted to milliseconds. Use
   isolated login windows and confirm request counts before attributing CPU to
   login. Check cold and warm successful/incorrect logins, ordinary pages/research,
   maximum/high percentiles and invocation outcomes. Mixed-request averages and
   local wall-clock benchmarks cannot establish the 10 ms edge allowance.
6. Stop if CPU, authentication or research gates fail. No upgrade, weaker hash,
   production deployment, routing change or merge is authorized by this document.

## Limitations and rollback

The replacement is built and tested locally only. Actual revised Cloudflare CPU
and revised live Render/SPY/QQQ behavior cannot be verified before the separately
approved backend release and candidate upload. Fail-closed 503 is expected if the
replacement Worker is used against a backend that lacks this endpoint.

The unchanged login HTML is hash-checked against the approved candidate. Browser
tests use only synthetic credentials and an isolated local verifier; this is not
evidence of live pricing or Cloudflare CPU compliance. Research fixture tests
retain SPY/QQQ archive provenance and do not fabricate live observations.

Local validation: production-context build and typecheck passed; 202 website unit
tests, 15 Worker/preflight tests, 47 browser tests and 12 focused Python auth tests
passed. The Python tests include the real FastAPI bearer boundary/native bcrypt
and the Worker session code through a loopback integration bridge. All 23 public
assets passed credential-reference scans. The Worker bundle contains no bcryptjs
implementation; bcryptjs remains available only to setup/test tooling.

The broad Python run reported 1,315 passes, 64 passing subtests, three failures
and six setup errors. Those cases involved Windows temp-directory permissions,
subprocess dependency paths and a Streamlit timeout. All 12 affected checks passed
in an isolated Python environment with a writable repository-local temp directory.
This is not a claim of a fresh all-green full-suite run in that corrected environment.

Rollback before activation means leaving the replacement undeployed. The endpoint
is additive, so it can remain unused without changing existing research/MCP.
Do not reactivate in-Worker bcrypt as a Workers Free production fallback. If a
later activated release fails, follow its separately approved traffic rollback
plan; no prior `alphaos-web` production deployment currently exists.
