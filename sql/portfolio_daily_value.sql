-- Portfolio valuation table in EUR.
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

-- Utility: add N business days (Mon-Fri) to a date.
create or replace function public.add_business_days(p_date date, p_days int)
returns date
language plpgsql
immutable
as $$
declare
  v_date date := p_date;
  v_remaining int := greatest(p_days, 0);
begin
  while v_remaining > 0 loop
    v_date := v_date + 1;
    if extract(isodow from v_date) between 1 and 5 then
      v_remaining := v_remaining - 1;
    end if;
  end loop;
  return v_date;
end;
$$;

-- Recompute/backfill valuations for a specific user under the new policy:
-- 1) one row on each month-end business day
-- 2) one row 2 business days after each net quantity change date
-- 3) value = sum((BUY qty - SELL qty) * market price) at valuation date
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

  -- No transactions -> clear existing valuations and exit.
  if v_min_txn_date is null then
    delete from public.portfolio_daily_value where user_id = p_user_id;
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
    -- Recompute with a rolling lookback to keep sparse valuation dates coherent
    -- around month boundaries and 2-business-day triggers.
    v_start_date := coalesce(v_last_saved_date - 45, v_min_txn_date);
    if v_start_date < v_min_txn_date then
      v_start_date := v_min_txn_date;
    end if;

    delete from public.portfolio_daily_value
    where user_id = p_user_id
      and valuation_date >= v_start_date;
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
    where t.user_id = p_user_id
      and t.txn_date::date between v_min_txn_date and p_as_of
  ),
  qty_change_dates as (
    -- Keep only days where net qty changes for at least one symbol.
    select d.txn_date as change_date
    from (
      select
        txn_date,
        symbol,
        sum(
          case when side = 'BUY' then quantity
               when side = 'SELL' then -quantity
               else 0 end
        ) as delta_qty
      from tx
      group by txn_date, symbol
    ) d
    group by d.txn_date
    having bool_or(abs(d.delta_qty) > 0)
  ),
  trigger_dates as (
    select public.add_business_days(q.change_date, 2) as valuation_date
    from qty_change_dates q
  ),
  month_starts as (
    select date_trunc('month', gs)::date as month_start
    from generate_series(date_trunc('month', v_start_date), date_trunc('month', p_as_of), interval '1 month') gs
  ),
  month_end_business_dates as (
    select max((ms.month_start + offs)::date) as valuation_date
    from month_starts ms
    cross join lateral generate_series(interval '0 day', interval '31 day', interval '1 day') offs
    where (ms.month_start + offs)::date >= ms.month_start
      and (ms.month_start + offs)::date < (ms.month_start + interval '1 month')::date
      and extract(isodow from (ms.month_start + offs)::date) between 1 and 5
    group by ms.month_start
  ),
  valuation_dates as (
    select distinct valuation_date
    from (
      select valuation_date from trigger_dates
      union all
      select valuation_date from month_end_business_dates
    ) s
    where valuation_date between v_start_date and p_as_of
  ),
  holdings as (
    select
      vd.valuation_date,
      tx.symbol,
      sum(
        case when tx.side = 'BUY' then tx.quantity
             when tx.side = 'SELL' then -tx.quantity
             else 0 end
      ) as qty
    from valuation_dates vd
    join tx
      on tx.txn_date <= vd.valuation_date
    group by vd.valuation_date, tx.symbol
    having sum(
      case when tx.side = 'BUY' then tx.quantity
           when tx.side = 'SELL' then -tx.quantity
           else 0 end
    ) > 0
  ),
  priced_holdings as (
    select
      h.valuation_date,
      h.symbol,
      h.qty,
      p.close_native,
      p.currency
    from holdings h
    left join lateral (
      select pd.close_native, pd.currency
      from public.prices_daily pd
      where upper(trim(pd.symbol)) = h.symbol
        and pd.date <= h.valuation_date
      order by pd.date desc
      limit 1
    ) p on true
  ),
  eur_valued as (
    select
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
    where ph.close_native is not null
  )
  insert into public.portfolio_daily_value (user_id, valuation_date, portfolio_value_eur, refreshed_at)
  select
    p_user_id,
    vd.valuation_date,
    coalesce(sum(ev.value_eur), 0)::numeric(20, 6) as portfolio_value_eur,
    now()
  from valuation_dates vd
  left join eur_valued ev
    on ev.valuation_date = vd.valuation_date
  group by vd.valuation_date
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

grant execute on function public.add_business_days(date, int) to authenticated;

-- One-time reset/rebuild (manual):
-- truncate table public.portfolio_daily_value;
-- select public.refresh_portfolio_daily_value('<user-uuid>', current_date, true);
