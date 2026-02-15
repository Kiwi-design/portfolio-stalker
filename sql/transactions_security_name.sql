-- Add persistent security name cache for ISIN symbols in transactions.
alter table if exists public.transactions
  add column if not exists security_name text;

-- Backfill existing NULL/empty placeholders so the UI never displays NULL.
update public.transactions
set security_name = upper(trim(symbol))
where security_name is null
   or btrim(security_name) = ''
   or lower(btrim(security_name)) = 'null';

comment on column public.transactions.security_name is
  'Cached security/fund name resolved from BNP Wealth Management for the ISIN stored in symbol';
