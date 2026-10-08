-- Runs only on disposable PostgreSQL after local_auth_harness.sql and
-- supabase/alphaos2_trade_ledger.sql. Any failed assertion fails CI.
\set ON_ERROR_STOP on

insert into auth.users(id) values
 ('00000000-0000-0000-0000-000000000101'),
 ('00000000-0000-0000-0000-000000000102');
insert into public.trade_positions(id,user_id,symbol,strategy_family,opened_at)
values
 ('00000000-0000-0000-0000-000000000201','00000000-0000-0000-0000-000000000101','QQQ','vertical',now()),
 ('00000000-0000-0000-0000-000000000202','00000000-0000-0000-0000-000000000102','SPY','vertical',now());
insert into public.trade_research_snapshots(id,user_id,symbol,observed_at,snapshot)
values
 ('00000000-0000-0000-0000-000000000301','00000000-0000-0000-0000-000000000101','QQQ',now(),'{}'),
 ('00000000-0000-0000-0000-000000000302','00000000-0000-0000-0000-000000000102','SPY',now(),'{}');
insert into public.trade_position_legs(position_id,leg_index,option_type,side,quantity,strike,expiration)
values
 ('00000000-0000-0000-0000-000000000201',0,'put','sell',1,500,'2027-01-15'),
 ('00000000-0000-0000-0000-000000000202',0,'put','sell',1,500,'2027-01-15');
insert into public.trade_events(position_id,user_id,event_type,occurred_at)
values
 ('00000000-0000-0000-0000-000000000201','00000000-0000-0000-0000-000000000101','entry',now()),
 ('00000000-0000-0000-0000-000000000202','00000000-0000-0000-0000-000000000102','entry',now());

grant select,insert,update,delete on public.trade_positions,
 public.trade_position_legs, public.trade_events, public.trade_research_snapshots
 to authenticated;

set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000101',false);

do $$
declare n integer;
begin
 select count(*) into n from public.trade_positions;
 if n <> 1 then raise exception 'RLS position select isolation failed: %',n; end if;
 select count(*) into n from public.trade_position_legs;
 if n <> 1 then raise exception 'RLS leg select isolation failed: %',n; end if;
 select count(*) into n from public.trade_events;
 if n <> 1 then raise exception 'RLS event select isolation failed: %',n; end if;
 select count(*) into n from public.trade_research_snapshots;
 if n <> 1 then raise exception 'RLS snapshot select isolation failed: %',n; end if;

 update public.trade_positions set notes='unauthorized'
  where id='00000000-0000-0000-0000-000000000202';
 get diagnostics n = row_count;
 if n <> 0 then raise exception 'Cross-user position update succeeded'; end if;
 delete from public.trade_events
  where position_id='00000000-0000-0000-0000-000000000202';
 get diagnostics n = row_count;
 if n <> 0 then raise exception 'Cross-user event delete succeeded'; end if;
end $$;

-- Unauthorized position ownership spoof must fail RLS.
do $$
begin
 begin
  insert into public.trade_positions(user_id,symbol,strategy_family,opened_at)
  values ('00000000-0000-0000-0000-000000000102','QQQ','vertical',now());
  raise exception 'Cross-user position insert unexpectedly succeeded';
 exception when insufficient_privilege then null;
 end;
end $$;

-- Critical nested-record test: user A must not attach an event to user B's
-- position even if the event.user_id claims A. A successful insert is a bug.
do $$
begin
 begin
  insert into public.trade_events(position_id,user_id,event_type,occurred_at)
  values ('00000000-0000-0000-0000-000000000202',
          '00000000-0000-0000-0000-000000000101','note',now());
  raise exception 'SECURITY FAILURE: cross-owner event reference accepted';
 exception when foreign_key_violation or check_violation or insufficient_privilege then null;
 end;
end $$;

-- Similarly, entry_snapshot_id must not point to another user's snapshot.
do $$
begin
 begin
  update public.trade_positions
    set entry_snapshot_id='00000000-0000-0000-0000-000000000302'
    where id='00000000-0000-0000-0000-000000000201';
  raise exception 'SECURITY FAILURE: cross-owner snapshot reference accepted';
 exception when foreign_key_violation or check_violation or insufficient_privilege then null;
 end;
end $$;

reset role;
