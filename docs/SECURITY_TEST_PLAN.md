# AlphaOS commercial security test gate

## Current coverage (PR #18)

- `tests/security/test_authorization_boundaries.py`: isolated authorization
  model, role matrix, cross-user denials, inactive memberships, invalid
  operations, personal ledger scoping, immutable context, and legacy research
  grants denied for ledger access.
- `tests/security/test_identity_fail_closed.py`: Supabase Auth adapter rejects
  malformed credentials, missing users, invalid IDs and provider exceptions;
  no live provider or credentials required.
- Existing `tests/test_tenancy.py`, `tests/test_supabase_identity.py` and
  `tests/test_identity_readiness_gate.py` provide additional unit coverage.
- Existing `.github/workflows/tests.yml` runs all pytest tests on pull requests.

**These are isolated unit tests, not a penetration test or proof of
production authorization.** In particular, tests with a mocked Supabase Auth
response do not verify token signature, expiration, revocation, or audience.
The commercial account-linking endpoint and database-backed membership
repository have not been implemented.

## Required integration gates before private routes

1. Provision an isolated Supabase test project or disposable local stack.
   Never point tests at production; use test-only users and sample trades.
2. Apply proposed migrations to test only. Test RLS as two independently
   authenticated users: user A cannot SELECT/INSERT/UPDATE/DELETE user B's
   positions, legs, events, snapshots, accounts, or saved research.
3. Verify nested ownership constraints, cross-user foreign keys, service-role
   code paths, concurrent writes, idempotency, and account deletion.
4. Exercise actual OAuth and account-linking HTTP flows: CSRF, PKCE, wrong
   client, wrong Supabase account, token expiry, refresh, revoke, replay,
   process restart, and denial without explicit consent.
5. Add MCP regression tests confirming all existing research tools remain
   callable with existing `research:read` authorization and that no private
   ledger tool is exposed to those grants.
6. Require green CI for the final PR SHA. Set required checks on the main
   branch in GitHub rulesets separately; this draft does not alter settings.

## Local and CI commands

```bash
python -m pytest -q tests/security
python -m pytest -q
```

GitHub Actions already runs the full suite for pull requests. The unit suite
must remain deterministic and not require production secrets. A separate
integration job can be added once an isolated test database is available.

**Deployment and migration status:** no production migrations, no deployment,
no Render settings changes, and no merge authorized by this document.

## Disposable local PostgreSQL integration job (added)

The `security-integration` GitHub Actions workflow starts a fresh PostgreSQL
16 service on the GitHub-hosted runner, creates a minimal local `auth.users`
and `auth.uid()` compatibility harness, applies the draft ledger SQL, and
executes `tests/security/sql/ledger_rls.sql` as an `authenticated` database
role. It verifies two-user row visibility, unauthorized updates/deletes and
inserts, and rejection of cross-owner event/snapshot references. It requires
no Supabase cloud project, paid plan, production credentials, or deployment.

**Limitations:** this is real PostgreSQL RLS enforcement but not the full
Supabase stack. The local `auth.uid()` shim is not a signed JWT verifier.
Actual Supabase Auth, PostgREST, account-linking OAuth, tenant membership
tables, and live endpoint integration still need separate tests.

To run: open GitHub Actions, choose `security-integration`, select
`alphaos2/identity-readiness-gate`, and run the workflow. Or inspect the
PR's `postgres-rls` check. No merge or production migration is required.

## Account-linking state machine prototype

`alphaos_api/account_link_state.py` is a **non-wired, process-local**
prototype. It uses opaque one-time tickets, grant/client binding, a required
explicit consent flag, expiry, revocation, and restart-fails-closed semantics.
`tests/security/test_account_link_state.py` tests replay, mismatch, consent,
expiry, revocation, and restart.

**This is not an authenticated account-linking flow.** `VerifiedGrant` and
`LedgerPrincipal` are plain Python objects; their construction does not prove
the caller verified an OAuth token or Supabase session. Before any route uses
this prototype, the trusted OAuth provider must resolve the actual token to a
grant identity and the browser session must be verified by Supabase Auth.
Bind approval to the browser's CSRF-protected session and independently
validated grant; do not accept grant fingerprints, verified flags, user IDs,
or consent values from arbitrary API request payloads. Confirm re-link and
account-switch behavior, token renewal, and grant revocation in HTTP-level
tests. A linked identity alone must never authorize private data: check
current grant scopes and user-owned database RLS at every operation.
