-- Additive market-candle quality metadata for the provider-neutral candle API.
-- This migration does not rewrite or backfill historical rows. Existing rows
-- retain NULL metadata, meaning "unknown/legacy" until a collector writes it.
-- Apply only after reviewing supabase/market_archive.sql in the target project.

alter table if exists public.market_candles
  add column if not exists session text,
  add column if not exists is_partial boolean,
  add column if not exists expected_bars integer,
  add column if not exists received_bars integer,
  add column if not exists completeness text;

comment on column public.market_candles.session is
  'Market session label for the bar; NULL means unknown/legacy.';
comment on column public.market_candles.is_partial is
  'Whether the provider identified the bar as still forming; NULL means unverified.';
comment on column public.market_candles.expected_bars is
  'Provider-reported expected bar count for the session, when available.';
comment on column public.market_candles.received_bars is
  'Provider-reported received bar count for the session, when available.';
comment on column public.market_candles.completeness is
  'complete, incomplete, or unknown; NULL means unclassified/legacy.';

create index if not exists market_candles_session_lookup
  on public.market_candles(symbol, aggregation, session, bar_time desc);
