-- Add persistent security name cache for ISIN symbols in transactions.
alter table if exists public.transactions
  add column if not exists security_name text;

-- Remove placeholder values from earlier versions.
update public.transactions
set security_name = null
where security_name is not null
  and (
    btrim(security_name) = ''
    or lower(btrim(security_name)) in ('null', 'none', 'undefined', 'n/a', 'na', '-')
    or upper(btrim(security_name)) = upper(trim(symbol))
  );

comment on column public.transactions.security_name is
  'Cached security/fund name resolved from BNP Wealth Management for the ISIN stored in symbol';
