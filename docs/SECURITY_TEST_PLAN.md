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
