-- Daily portfolio valuation table in EUR.
-- Paste this in Supabase SQL Editor.

create table if not exists public.portfolio_daily_value (
  user_id uuid not null references auth.users (id) on delete cascade,
  valuation_date date not null,
  portfolio_value_eur numeric(20, 6) not null,
  refreshed_at timestamptz not null default now(),
  primary key (user_id, valuation_date)
);

create index if not exists portfolio_daily_value_user_date_idx
  on public.portfolio_daily_value (user_id, valuation_date desc);

-- Recompute / backfill daily valuations for a specific user.
-- p_rebuild=false: only fills missing days + refreshes the latest day up to p_as_of.
-- p_rebuild=true: rebuilds full history for the user.
create or replace function public.refresh_portfolio_daily_value(
  p_user_id uuid,
  p_as_of date default current_date,
  p_rebuild boolean default false
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_min_txn_date date;
  v_last_saved_date date;
  v_start_date date;
begin
  if p_user_id is null then
    raise exception 'p_user_id is required';
  end if;

  select min(t.txn_date)::date
    into v_min_txn_date
  from public.transactions t
  where t.user_id = p_user_id
    and t.txn_date is not null;

  -- No transactions -> nothing to build.
  if v_min_txn_date is null then
    return;
  end if;

  select max(v.valuation_date)
    into v_last_saved_date
  from public.portfolio_daily_value v
  where v.user_id = p_user_id;

  if p_rebuild then
    delete from public.portfolio_daily_value where user_id = p_user_id;
    v_start_date := v_min_txn_date;
  else
    -- Backfill missing dates and refresh latest day at login.
    -- Example: if user skips 2 days, next login inserts those two days + today.
    v_start_date := coalesce(v_last_saved_date, v_min_txn_date);
    if v_start_date < v_min_txn_date then
      v_start_date := v_min_txn_date;
    end if;
  end if;

  if v_start_date > p_as_of then
    return;
  end if;

  with tx as (
    select
      t.user_id,
      upper(trim(t.symbol)) as symbol,
      t.side,
      t.quantity::numeric as quantity,
      t.txn_date::date as txn_date
    from public.transactions t
    where t.txn_date is not null
      and t.user_id = p_user_id
  ),
  daily_calendar as (
    select p_user_id as user_id, gs::date as valuation_date
    from generate_series(v_start_date, p_as_of, interval '1 day') gs
  ),
  holdings as (
    select
      c.user_id,
      c.valuation_date,
      t.symbol,
      sum(
        case when t.side = 'BUY' then t.quantity
             when t.side = 'SELL' then -t.quantity
             else 0 end
      ) as qty
    from daily_calendar c
    join tx t
      on t.txn_date <= c.valuation_date
    group by c.user_id, c.valuation_date, t.symbol
    having sum(
      case when t.side = 'BUY' then t.quantity
           when t.side = 'SELL' then -t.quantity
           else 0 end
    ) > 0
  ),
  priced_holdings as (
    select
      h.user_id,
      h.valuation_date,
      h.symbol,
      h.qty,
      p.close_native,
      p.currency,
      lb.last_buy_price_eur
    from holdings h
    left join lateral (
      select pd.close_native, pd.currency
      from public.prices_daily pd
      where upper(trim(pd.symbol)) = h.symbol
        and pd.date <= h.valuation_date
      order by pd.date desc
      limit 1
    ) p on true
    left join lateral (
      select t.price::numeric as last_buy_price_eur
      from public.transactions t
      where t.user_id = h.user_id
        and upper(trim(t.symbol)) = h.symbol
        and t.side = 'BUY'
        and t.txn_date <= h.valuation_date
      order by t.txn_date desc, t.created_at desc
      limit 1
    ) lb on true
  ),
  eur_valued as (
    select
      ph.user_id,
      ph.valuation_date,
      case
        when ph.close_native is not null then
          ph.qty * ph.close_native * (
            case
              when ph.currency = 'EUR' then 1
              when fx.eur_to_ccy is not null and fx.eur_to_ccy <> 0 then 1 / fx.eur_to_ccy
              else null
            end
          )
        when ph.last_buy_price_eur is not null then
          ph.qty * ph.last_buy_price_eur
        else null
      end as value_eur
    from priced_holdings ph
    left join lateral (
      select f.eur_to_ccy
      from public.fx_daily f
      where f.ccy = ph.currency
        and f.date <= ph.valuation_date
      order by f.date desc
      limit 1
    ) fx on ph.currency <> 'EUR'
    where ph.close_native is not null or ph.last_buy_price_eur is not null
  )
  insert into public.portfolio_daily_value (user_id, valuation_date, portfolio_value_eur, refreshed_at)
  select
    c.user_id,
    c.valuation_date,
    coalesce(sum(e.value_eur), 0)::numeric(20, 6) as portfolio_value_eur,
    now()
  from daily_calendar c
  left join eur_valued e
    on e.user_id = c.user_id
   and e.valuation_date = c.valuation_date
  group by c.user_id, c.valuation_date
  on conflict (user_id, valuation_date)
  do update set
    portfolio_value_eur = excluded.portfolio_value_eur,
    refreshed_at = now();
end;
$$;

-- Call this from the client right after login/session restore.
-- It uses auth.uid() so each user can only refresh their own rows.
create or replace function public.refresh_portfolio_daily_value_on_login(
  p_as_of date default current_date
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid uuid;
begin
  v_uid := auth.uid();
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;

  perform public.refresh_portfolio_daily_value(v_uid, p_as_of, false);
end;
$$;

grant execute on function public.refresh_portfolio_daily_value_on_login(date) to authenticated;

-- Manual examples:
-- select public.refresh_portfolio_daily_value_on_login();
-- select public.refresh_portfolio_daily_value('<user-uuid>', current_date, true); -- full rebuild
