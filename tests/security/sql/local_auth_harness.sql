-- Disposable PostgreSQL compatibility harness for AlphaOS ledger RLS.
-- NOT a complete Supabase Auth implementation. Never run against production.
create schema if not exists auth;
create role authenticated nologin;
create table auth.users (id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
create function public.set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
grant usage on schema public to authenticated;
grant usage on schema auth to authenticated;
