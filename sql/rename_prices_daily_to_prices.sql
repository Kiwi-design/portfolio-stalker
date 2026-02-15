-- Rename legacy daily price cache table to event-based prices table.
-- Safe to run multiple times.

do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'public' and table_name = 'prices_daily'
  ) and not exists (
    select 1
    from information_schema.tables
    where table_schema = 'public' and table_name = 'prices'
  ) then
    execute 'alter table public.prices_daily rename to prices';
  end if;
end $$;

create table if not exists public.prices (
  symbol text not null,
  date date not null,
  close_native double precision not null,
  currency text not null,
  source text,
  updated_at timestamptz,
  primary key(symbol, date)
);

create index if not exists prices_symbol_date_idx
  on public.prices(symbol, date desc);
