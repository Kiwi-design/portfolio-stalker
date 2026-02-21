-- Remove deprecated cache tables that are no longer part of the runtime flow.
-- Safe to run multiple times.

begin;

-- Remove RPCs that depend on portfolio_daily_value.
drop function if exists public.refresh_portfolio_daily_value_on_login(date);
drop function if exists public.refresh_portfolio_daily_value(uuid, date, boolean);

-- Remove cache tables.
drop table if exists public.asset_event_prices;
drop table if exists public.portfolio_daily_value;
drop table if exists public.prices;

commit;
