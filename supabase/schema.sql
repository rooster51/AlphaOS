create extension if not exists "pgcrypto";

create table if not exists public.user_settings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  display_name text,
  default_account_size numeric(14, 2) default 0,
  default_risk_pct numeric(6, 3) default 1.0,
  timezone text default 'America/New_York',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id)
);

create table if not exists public.watchlist (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  notes text,
  score numeric(6, 2) default 50,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, symbol)
);

create table if not exists public.trades (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  side text not null check (side in ('Long', 'Short')),
  status text not null check (status in ('Open', 'Closed')),
  strategy text,
  entry_date date not null,
  exit_date date,
  quantity numeric(18, 6) not null default 0,
  entry_price numeric(18, 6) not null default 0,
  exit_price numeric(18, 6),
  pnl numeric(18, 2),
  fees numeric(18, 2) default 0,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.daily_pnl_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  snapshot_date date not null,
  realized_pnl numeric(18, 2) not null default 0,
  unrealized_pnl numeric(18, 2) not null default 0,
  equity numeric(18, 2),
  created_at timestamptz not null default now(),
  unique(user_id, snapshot_date)
);

alter table public.user_settings enable row level security;
alter table public.watchlist enable row level security;
alter table public.trades enable row level security;
alter table public.daily_pnl_snapshots enable row level security;

create policy "Users can read own settings"
  on public.user_settings for select
  using (auth.uid() = user_id);

create policy "Users can insert own settings"
  on public.user_settings for insert
  with check (auth.uid() = user_id);

create policy "Users can update own settings"
  on public.user_settings for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can manage own watchlist"
  on public.watchlist for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can manage own trades"
  on public.trades for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can manage own pnl snapshots"
  on public.daily_pnl_snapshots for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists set_user_settings_updated_at on public.user_settings;
create trigger set_user_settings_updated_at
before update on public.user_settings
for each row execute function public.set_updated_at();

drop trigger if exists set_watchlist_updated_at on public.watchlist;
create trigger set_watchlist_updated_at
before update on public.watchlist
for each row execute function public.set_updated_at();

drop trigger if exists set_trades_updated_at on public.trades;
create trigger set_trades_updated_at
before update on public.trades
for each row execute function public.set_updated_at();
