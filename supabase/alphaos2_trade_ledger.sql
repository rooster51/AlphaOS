-- AlphaOS 2.0 trade ledger foundation.
-- Additive only: the legacy public.trades table remains untouched.

create table if not exists public.trade_positions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  strategy_family text not null,
  status text not null default 'open' check (status in ('open','closed','cancelled')),
  opened_at timestamptz not null,
  closed_at timestamptz,
  quantity numeric(18,6) not null default 1 check (quantity > 0),
  entry_snapshot_id uuid,
  source text not null default 'alphaos',
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.trade_position_legs (
  id uuid primary key default gen_random_uuid(),
  position_id uuid not null references public.trade_positions(id) on delete cascade,
  leg_index integer not null check (leg_index >= 0),
  option_type text not null check (option_type in ('call','put')),
  side text not null check (side in ('buy','sell')),
  quantity numeric(18,6) not null check (quantity > 0),
  strike numeric(18,6) not null check (strike > 0),
  expiration date not null,
  contract_symbol text,
  created_at timestamptz not null default now(),
  unique(position_id, leg_index)
);

create table if not exists public.trade_research_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  observed_at timestamptz not null,
  model_version text,
  snapshot_type text not null default 'entry',
  snapshot jsonb not null,
  created_at timestamptz not null default now()
);

alter table public.trade_positions
  drop constraint if exists trade_positions_entry_snapshot_id_fkey;
alter table public.trade_positions
  add constraint trade_positions_entry_snapshot_id_fkey
  foreign key (entry_snapshot_id) references public.trade_research_snapshots(id) on delete set null;

create table if not exists public.trade_events (
  id uuid primary key default gen_random_uuid(),
  position_id uuid not null references public.trade_positions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null check (event_type in ('entry','add','partial_exit','adjust','roll','close','fee','note','correction')),
  occurred_at timestamptz not null,
  quantity numeric(18,6),
  net_price numeric(18,6),
  cash_flow numeric(18,2),
  fees numeric(18,2) not null default 0 check (fees >= 0),
  underlying_price numeric(18,6),
  research_snapshot_id uuid references public.trade_research_snapshots(id) on delete set null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists trade_positions_user_status_idx on public.trade_positions(user_id,status,opened_at desc);
create index if not exists trade_events_position_time_idx on public.trade_events(position_id,occurred_at);
create index if not exists trade_snapshots_user_symbol_time_idx on public.trade_research_snapshots(user_id,symbol,observed_at desc);

alter table public.trade_positions enable row level security;
alter table public.trade_position_legs enable row level security;
alter table public.trade_research_snapshots enable row level security;
alter table public.trade_events enable row level security;

create policy "Users can manage own trade positions" on public.trade_positions for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can manage own research snapshots" on public.trade_research_snapshots for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can manage own trade events" on public.trade_events for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can manage legs for own positions" on public.trade_position_legs for all
  using (exists (select 1 from public.trade_positions p where p.id=position_id and p.user_id=auth.uid()))
  with check (exists (select 1 from public.trade_positions p where p.id=position_id and p.user_id=auth.uid()));

drop trigger if exists set_trade_positions_updated_at on public.trade_positions;
create trigger set_trade_positions_updated_at before update on public.trade_positions
for each row execute function public.set_updated_at();

-- Cross-owner references must be rejected even when the child row's user_id
-- matches the caller. Composite keys make the ownership invariant structural.
create unique index if not exists trade_positions_user_id_id_unique
  on public.trade_positions(user_id,id);
create unique index if not exists trade_snapshots_user_id_id_unique
  on public.trade_research_snapshots(user_id,id);

alter table public.trade_events
  add constraint trade_events_same_owner_position
  foreign key (user_id,position_id)
  references public.trade_positions(user_id,id) on delete cascade;

alter table public.trade_events
  add constraint trade_events_same_owner_snapshot
  foreign key (user_id,research_snapshot_id)
  references public.trade_research_snapshots(user_id,id);

alter table public.trade_positions
  add constraint trade_positions_same_owner_entry_snapshot
  foreign key (user_id,entry_snapshot_id)
  references public.trade_research_snapshots(user_id,id);
