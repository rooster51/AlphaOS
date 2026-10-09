# AlphaOS commercial architecture — advanced quantitative options traders

**Status:** design and isolated domain-model groundwork only. No migration,
endpoint, MCP tool, OAuth grant, deployment, or billing flow is activated.

## Product boundaries

AlphaOS is a quantitative options research and trade-intelligence platform
for advanced retail traders. The initial product offers market regime research,
cross-structure payoff/scenario analysis, saved research, personal trade journal,
and performance attribution. It does not execute trades or promise returns.

**Control plane:** Supabase Auth users, customer tenant/workspace membership,
roles, subscriptions, API keys and quotas. A person can belong to multiple
workspaces. A workspace is not a brokerage account.

**Research plane:** versioned, timestamped shared market/archive data and
deterministic research engines. Market data is not owned by a tenant; user
watchlists, private notes and saved analyses are. Cache keys include model
version, observation timestamps and inputs; no private user inputs in global
cache entries.

**Private data plane:** personal portfolios, brokerage account connections,
positions, fills, events, journal and research snapshots. Ownership is enforced
by verified user and account scope. Shared/team journals require an explicit
future sharing model, never implicit tenant-wide access.

**Client plane:** ChatGPT MCP, web dashboard, future mobile and service API.
Each client authenticates independently to the same identity/authorization
service. A shared backend service credential does not identify the caller.

## Proposed database schema (NOT APPLIED)

- `customer_tenants(id, name, created_by, created_at)`
- `tenant_memberships(tenant_id, user_id, role, status, created_at)`
  with unique membership and role constraints
- `customer_accounts(id, owner_user_id, tenant_id nullable, label, broker,
  external_reference_hash nullable)` — accounts are private by default
- `tenant_entitlements(tenant_id, plan, feature, quota, period, status)`
- `research_requests(id, user_id, tenant_id nullable, model_version, ...)`
  with per-customer audit and metering, distinct from shared archive data
- Existing `trade_positions`, `trade_events`, `trade_position_legs`,
  and `trade_research_snapshots` retain `user_id` ownership and RLS.
  Introduce account_id and tenant sharing only in a separately reviewed
  additive migration with same-owner foreign-key constraints.

Enforce RLS for each private table. Service-role access bypasses RLS and
therefore requires an explicit server-side authorization check and scoped
queries; prefer end-user JWT/RLS for private CRUD. Nested legs/events/snapshots
must reference records owned by the same user. Cross-tenant tests are required.

## Authentication and migration

1. Supabase Auth verifies individual user sessions. Only the trusted server
   resolves actor IDs; never accept `user_id`, `verified` or role flags from
   request parameters.
2. Preserve legacy MCP OAuth `research:read` and literal `owner` semantics
   strictly for existing research. It never implies ledger or tenant access.
3. Implement a separate, CSRF-protected browser account-linking consent that
   verifies both the ChatGPT OAuth session and Supabase Auth session. Bind the
   link to the grant/client and actual verified user, with expiration,
   revocation, and a fail-closed restart policy. This is NOT implemented.
4. Future MCP scopes and REST routes for private data must be independently
   authorized; adding a scope string alone is not authorization.
5. Introduce a compatibility plan for the first user's data; never silently
   assign all legacy records to the first new account.

## Advanced trader experience

- Discover: classify regime, price structure, implied versus realized moves,
  event risks and candidate structures with evidence and unknowns.
- Analyze: compare long premium, debit/credit spreads, calendars, diagonals,
  butterflies, broken-wing butterflies and iron condors only when each model
  and required data are validated.
- Journal: immutable trade lifecycle events, partial fills/exits, fees,
  realized/unrealized P&L, attribution by structure, DTE and market regime.
- Improve: performance analytics with sample sizes, uncertainty and bias
  disclosures. No fabricated probability of profit or guaranteed expectancy.
- Guardrails: entitlement checks, usage metering, quote freshness,
  rate limiting, audit trails, retention and user data export/deletion.

## Commercial release gates

- Automated unit/integration security tests: user A cannot read or mutate
  user B's account, nested events, snapshots, research notes or entitlements;
  revoked memberships and expired grants fail closed.
- Migration dry run and rollback plan in staging; RLS tested under
  authenticated user and service roles.
- Research parity tests for all current MCP tools and OAuth flows.
- Load tests, per-user quotas, structured observability and cost limits.
- Verify market-data redistribution/commercial licensing, privacy policy,
  terms, data retention, brokerage integration rules and applicable
  investment-advice/compliance obligations before offering paid service.
- Explicit review and approval before merging, production migrations,
  deployment or modifying Render environment settings.

## PR #18 scope

`alphaos_api/tenancy.py` and `tests/test_tenancy.py` are intentionally
unwired, dependency-free models/tests. They do not establish an authenticated
request context, persist memberships, authorize database queries, or enable
customer registration. The existing Supabase token verifier is also unwired.
No production-readiness claim is implied.

## PR #18 follow-on: workspace RLS draft

`supabase/alphaos2_tenancy.sql` now defines customer workspaces and
memberships with RLS. Users can read their own membership and active
workspaces; clients cannot grant, revoke, or modify memberships. An isolated
PostgreSQL integration test exercises cross-tenant visibility, membership
mutation denial, and revocation. This is not deployed.

**Important bootstrap constraint:** creating a workspace does not automatically
create its owner membership. Provisioning must be implemented as a reviewed
transaction in a trusted server component with authenticated creator binding,
idempotency, auditing, and rollback. Never expose a generic service-role
membership mutation endpoint. The legacy MCP research grant remains
research-only.

**Account-linking design gate:** the current process-local OAuth grant's
literal `owner` subject is not a Supabase user. No ChatGPT-to-Supabase link
can be inferred from that token. A future link must authenticate the user
through Supabase, verify the requesting OAuth grant and client, require
explicit user approval, bind only that grant to the verified Supabase user,
and enforce expiry/revocation. Do not enable private MCP routes before those
end-to-end negative tests pass.
