-- Add persistent security name cache for ISIN symbols in transactions.
alter table if exists public.transactions
  add column if not exists security_name text;

comment on column public.transactions.security_name is
  'Cached security/fund name resolved from BNP Wealth Management for the ISIN stored in symbol';
