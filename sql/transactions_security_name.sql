-- Add persistent security metadata cache for ISIN symbols in transactions.
alter table if exists public.transactions
  add column if not exists security_name text;

alter table if exists public.transactions
  add column if not exists txn_close_price text;

-- Remove placeholder values from earlier versions.
update public.transactions
set security_name = null
where security_name is not null
  and (
    btrim(security_name) = ''
    or lower(btrim(security_name)) in ('null', 'none', 'undefined', 'n/a', 'na', '-')
    or upper(btrim(security_name)) = upper(trim(symbol))
  );

update public.transactions
set txn_close_price = 'unavailable'
where txn_close_price is null or btrim(txn_close_price) = '';

-- Reuse any already-known valid name for the same user + ISIN to fill NULL rows.
with canonical as (
  select
    user_id,
    upper(trim(symbol)) as symbol_norm,
    min(security_name) as canonical_name
  from public.transactions
  where security_name is not null
    and btrim(security_name) <> ''
    and upper(btrim(security_name)) <> upper(trim(symbol))
  group by user_id, upper(trim(symbol))
)
update public.transactions t
set security_name = c.canonical_name
from canonical c
where t.user_id = c.user_id
  and upper(trim(t.symbol)) = c.symbol_norm
  and (t.security_name is null or btrim(t.security_name) = '');

comment on column public.transactions.security_name is
  'Cached security/fund name resolved from EODHD for the ISIN entered by the user';
comment on column public.transactions.txn_close_price is
  'Closing price on transaction date from EODHD lookup; set to unavailable when not retrievable';
