-- Additive migration; existing observed_at values and archives are unchanged.
alter table public.option_snapshots add column if not exists slot_time timestamptz;
create unique index if not exists option_snapshots_slot_unique
  on public.option_snapshots(provider, symbol, slot_time) where slot_time is not null;
-- Legacy rows have no verified slot/observation distinction; do not backfill.
