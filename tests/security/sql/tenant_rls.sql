\set ON_ERROR_STOP on
insert into public.customer_tenants(id,name,created_by) values
 ('00000000-0000-0000-0000-000000000401','Workspace A','00000000-0000-0000-0000-000000000101'),
 ('00000000-0000-0000-0000-000000000402','Workspace B','00000000-0000-0000-0000-000000000102');
insert into public.tenant_memberships(tenant_id,user_id,role,status) values
 ('00000000-0000-0000-0000-000000000401','00000000-0000-0000-0000-000000000101','owner','active'),
 ('00000000-0000-0000-0000-000000000402','00000000-0000-0000-0000-000000000102','owner','active');
grant select,insert,update,delete on public.customer_tenants,public.tenant_memberships to authenticated;
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000101',false);
do $$
declare n int;
begin
 select count(*) into n from public.customer_tenants;
 if n<>1 then raise exception 'Cross-tenant workspace visibility failed'; end if;
 select count(*) into n from public.tenant_memberships;
 if n<>1 then raise exception 'Membership privacy failed'; end if;
 update public.tenant_memberships set role='admin'
 where tenant_id='00000000-0000-0000-0000-000000000401';
 get diagnostics n=row_count;
 if n<>0 then raise exception 'Client membership update unexpectedly allowed'; end if;
 delete from public.tenant_memberships
 where tenant_id='00000000-0000-0000-0000-000000000401';
 get diagnostics n=row_count;
 if n<>0 then raise exception 'Client membership deletion unexpectedly allowed'; end if;
end $$;
do $$
begin
 begin
  insert into public.tenant_memberships(tenant_id,user_id,role)
  values ('00000000-0000-0000-0000-000000000402',
   '00000000-0000-0000-0000-000000000101','owner');
  raise exception 'SECURITY FAILURE: client membership insert accepted';
 exception when insufficient_privilege then null;
 end;
end $$;
reset role;
update public.tenant_memberships set status='revoked'
 where tenant_id='00000000-0000-0000-0000-000000000401';
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000101',false);
do $$
declare n int;
begin
 select count(*) into n from public.customer_tenants;
 if n<>0 then raise exception 'Revoked membership still grants workspace visibility'; end if;
end $$;
reset role;
