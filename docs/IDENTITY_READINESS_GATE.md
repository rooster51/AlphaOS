# AlphaOS 2.0 identity and deployment gate (draft)

## Scope
This branch introduces an **isolated, unused** identity boundary and a local,
side-effect-free deployment configuration assessor. No existing REST or MCP
routes, OAuth grants, research tools, database policies, Render settings or
GitHub Actions have been changed. No ledger operations are enabled.

## Current identity limitation
The REST API authenticates a shared `ALPHAOS_API_TOKEN` and returns no verified
Supabase user. The existing MCP OAuth issues process-local research grants
with the literal subject `owner`; MCP invokes REST with the shared token.
Streamlit Supabase login is a separate trust boundary. None can authorize
owner-scoped trade-ledger writes. A UUID passed in request data is untrusted.

## Proposed trusted identity integration (not implemented)
1. Select a user-bound identity provider (prefer Supabase Auth for consistency
   with `auth.users`), with issuer and audience configured out of band.
2. Implement server-side verification of signed user access tokens using
   provider-published keys and allowed algorithms, including issuer, audience,
   expiry, not-before, token type and session/revocation requirements.
3. Bind the verified subject to `auth.users.id`. Never accept a client-supplied
   user ID or a service-role request as evidence of the calling user.
4. Introduce a **separate ledger authorization boundary**; existing research
   grants retain `research:read` only. Keep current OAuth flows untouched.
5. Prefer per-user Supabase JWT/RLS enforcement. If privileged server access
   is necessary, enforce owner filters and same-owner constraints transactionally.
6. Design immutable events, idempotency, over-close protection, fee allocation,
   corrections, and partial-close semantics before enabling any write routes.
7. Test cross-user isolation, forged/expired tokens, key rotation, restart,
   retries, concurrent closes, and fail-closed missing configuration.

`require_ledger_principal` is **not** a token verifier. Its `verified=True`
argument is only safe when supplied by a future trusted server-side verifier,
never from request data. It is not wired to any API route.

## Supabase Auth verifier (isolated implementation)

`alphaos_api/supabase_identity.py` introduces `verify_supabase_access_token`.
It sends the presented access token to Supabase Auth `get_user` using a public
anon/publishable key, and accepts only a user returned by that authenticated
provider response. The provider handles token signature, expiry and session
validation. A server-side failure rejects access without reflecting provider
errors. This is **not** local JWKS verification and is not connected to any
route or MCP tool.

Future integration requires configuring `SUPABASE_ANON_KEY` (or an explicitly
validated publishable key) in the server environment and designing account
linking for ChatGPT OAuth separately. Do not infer that existing research grants
identify a Supabase user. No write authorization is enabled.

## Deployment gate
`assess_readiness` checks local presence of five required configuration
values and HTTPS origin syntax, returning only missing/invalid field names.
It does **not** prove live Render settings, service-role permissions, archive
coverage, runtime parity, connector registration, or database migrations.

Production remains **NO-GO** until the independent readiness checklist in
`docs/PRODUCTION_READINESS.md` is completed and explicitly approved.
Do not put Supabase secrets in GitHub or PR discussions. Configure them directly
in Render only under separate authorization.

## Verification
Run `python -m pytest -q tests/test_identity_readiness_gate.py` and the full
`python -m pytest -q` suite. Require green CI on the final PR SHA before
considering review. This draft does not claim live deployment validation.
