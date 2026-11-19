begin;

create schema market_playbook_private;
revoke all on schema market_playbook_private from public, anon, authenticated;
grant usage on schema market_playbook_private to service_role;

create table market_playbook_private.thesis (
    id text primary key,
    symbol text not null check (symbol in ('SPY', 'QQQ')),
    provider text not null,
    session_date date not null,
    evidence jsonb not null check (jsonb_typeof(evidence) = 'object')
);

create index market_playbook_recent
    on market_playbook_private.thesis (symbol, provider, session_date desc, id);

create table market_playbook_private.event (
    thesis_id text not null references market_playbook_private.thesis(id),
    sequence integer not null check (sequence >= 0),
    observation jsonb not null check (jsonb_typeof(observation) = 'object'),
    primary key (thesis_id, sequence)
);

alter table market_playbook_private.thesis enable row level security;
alter table market_playbook_private.event enable row level security;
revoke all on all tables in schema market_playbook_private from public, anon, authenticated, service_role;
grant select, insert on all tables in schema market_playbook_private to service_role;

-- Read the current revision, then compare and append atomically. A changed
-- revision prompts the caller to recalculate against the committed thesis.
create function public.market_playbook_journal(
    p_symbol text, p_provider text, p_as_of date,
    p_expected_revision text, p_updates jsonb
) returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    records jsonb;
    revision text;
    applied boolean := false;
    entry jsonb;
begin
    if p_expected_revision is not null then
        perform pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended('market-playbook/' || p_symbol || '/' || p_provider, 0)
        );
    end if;

    select coalesce(jsonb_agg(
        jsonb_build_object('thesis', t.evidence, 'events', coalesce(e.items, '[]'::jsonb))
        order by t.session_date desc, t.id
    ), '[]'::jsonb)
    into records
    from (
        select id, session_date, evidence from market_playbook_private.thesis
        where symbol = p_symbol and provider = p_provider and session_date <= p_as_of
        order by session_date desc, id limit 20
    ) t
    cross join lateral (
        select jsonb_agg(observation order by sequence) as items
        from market_playbook_private.event where thesis_id = t.id
    ) e;

    revision := md5(records::text);
    if p_expected_revision = revision then
        for entry in select value from jsonb_array_elements(p_updates)
        loop
            if entry ? 'thesis' then
                insert into market_playbook_private.thesis (id, symbol, provider, session_date, evidence)
                values (entry->>'id', p_symbol, p_provider, p_as_of, entry->'thesis');
            end if;
            insert into market_playbook_private.event (thesis_id, sequence, observation)
            select entry->>'id', (entry->>'after')::integer + ordinal::integer - 1, observation
            from jsonb_array_elements(entry->'events') with ordinality as e(observation, ordinal)
            where exists (
                select 1 from market_playbook_private.thesis
                where id = entry->>'id' and symbol = p_symbol and provider = p_provider
            );
        end loop;
        applied := true;
    end if;

    return jsonb_build_object('revision', revision, 'records', records, 'applied', applied);
end;
$$;

revoke all on function public.market_playbook_journal(text, text, date, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.market_playbook_journal(text, text, date, text, jsonb)
    to service_role;

commit;
