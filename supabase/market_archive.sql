-- AlphaOS persistent market archive + options journal foundation.
-- Apply after supabase/schema.sql.

create table if not exists public.market_candles (
  id bigint generated always as identity primary key,
  provider text not null,
  symbol text not null,
  aggregation text not null,
  bar_time timestamptz not null,
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  volume numeric,
  retrieved_at timestamptz not null default now(),
  unique(provider, symbol, aggregation, bar_time)
);

create index if not exists market_candles_lookup
  on public.market_candles(symbol, aggregation, bar_time desc);

create table if not exists public.option_snapshots (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  symbol text not null,
  observed_at timestamptz not null,
  session_date date not null,
  underlying_price numeric,
  min_dte integer,
  max_dte integer,
  strike_band numeric,
  contract_count integer not null default 0,
  archive_path text not null,
  archive_sha256 text,
  quality_status text,
  created_at timestamptz not null default now(),
  unique(provider, symbol, observed_at)
);

create index if not exists option_snapshots_lookup
  on public.option_snapshots(symbol, observed_at desc);

create table if not exists public.market_daily_snapshots (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  symbol text not null,
  session_date date not null,
  observed_at timestamptz not null,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  volume numeric,
  previous_close numeric,
  option_snapshot_id uuid references public.option_snapshots(id) on delete set null,
  context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(provider, symbol, session_date)
);

alter table public.trades
  add column if not exists opened_at timestamptz,
  add column if not exists closed_at timestamptz,
  add column if not exists opening_credit numeric(18,6),
  add column if not exists opening_debit numeric(18,6),
  add column if not exists closing_credit numeric(18,6),
  add column if not exists closing_debit numeric(18,6),
  add column if not exists expiration_date date,
  add column if not exists market_snapshot_id uuid references public.option_snapshots(id) on delete set null,
  add column if not exists source text default 'alphaos';

create table if not exists public.trade_legs (
  id uuid primary key default gen_random_uuid(),
  trade_id uuid not null references public.trades(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  option_symbol text,
  option_type text check (option_type in ('CALL','PUT')),
  position_side text not null check (position_side in ('LONG','SHORT')),
  strike numeric(18,6),
  expiration_date date,
  quantity numeric(18,6) not null default 1,
  created_at timestamptz not null default now()
);

create index if not exists trade_legs_trade_id on public.trade_legs(trade_id);

create table if not exists public.trade_executions (
  id uuid primary key default gen_random_uuid(),
  trade_id uuid not null references public.trades(id) on delete cascade,
  trade_leg_id uuid references public.trade_legs(id) on delete set null,
  user_id uuid not null references auth.users(id) on delete cascade,
  execution_type text not null check (execution_type in ('OPEN','CLOSE','ADJUST')),
  executed_at timestamptz not null,
  quantity numeric(18,6) not null,
  price numeric(18,6) not null,
  fees numeric(18,2) not null default 0,
  notes text,
  created_at timestamptz not null default now()
);

create index if not exists trade_executions_trade_id
  on public.trade_executions(trade_id, executed_at);

alter table public.market_candles enable row level security;
alter table public.option_snapshots enable row level security;
alter table public.market_daily_snapshots enable row level security;
alter table public.trade_legs enable row level security;
alter table public.trade_executions enable row level security;

create policy "Authenticated users can read market candles"
  on public.market_candles for select to authenticated using (true);
create policy "Authenticated users can read option snapshots"
  on public.option_snapshots for select to authenticated using (true);
create policy "Authenticated users can read daily market snapshots"
  on public.market_daily_snapshots for select to authenticated using (true);

create policy "Users can manage own trade legs"
  on public.trade_legs for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can manage own trade executions"
  on public.trade_executions for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Full raw option-chain observations live in Storage rather than bloating Postgres.
insert into storage.buckets (id, name, public)
values ('market-archive', 'market-archive', false)
on conflict (id) do update set public = false;

create policy "Authenticated users can read market archive objects"
  on storage.objects for select to authenticated
  using (bucket_id = 'market-archive');
