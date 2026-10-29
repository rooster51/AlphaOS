-- Draft commercial workspace membership schema. Apply only to disposable test DB.
create table if not exists public.customer_tenants (
 id uuid primary key default gen_random_uuid(),
 name text not null check(length(trim(name)) between 1 and 120),
 created_by uuid not null references auth.users(id),
 created_at timestamptz not null default now()
);
create table if not exists public.tenant_memberships (
 tenant_id uuid not null references public.customer_tenants(id) on delete cascade,
 user_id uuid not null references auth.users(id) on delete cascade,
 role text not null check(role in ('owner','admin','analyst','viewer')),
 status text not null default 'active' check(status in ('active','revoked')),
 created_at timestamptz not null default now(),
 primary key(tenant_id,user_id)
);
create index if not exists tenant_memberships_user_idx on public.tenant_memberships(user_id,tenant_id);
alter table public.customer_tenants enable row level security;
alter table public.tenant_memberships enable row level security;
-- Owners create their own workspace; no ability to claim another creator.
create policy tenant_creator_insert on public.customer_tenants for insert to authenticated
 with check(created_by=auth.uid());
create policy tenant_members_read on public.customer_tenants for select to authenticated
 using(exists(select 1 from public.tenant_memberships m
 where m.tenant_id=id and m.user_id=auth.uid() and m.status='active'));
-- Members can see only their own membership, preventing team roster leakage.
create policy membership_self_read on public.tenant_memberships for select to authenticated
 using(user_id=auth.uid());
-- Intentionally no client-facing membership INSERT/UPDATE/DELETE policies.
-- Membership provisioning and role changes require a separately audited
-- privileged server-side operation; creator ownership alone grants no roles.
