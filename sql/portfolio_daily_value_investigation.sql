-- Investigate how a portfolio_daily_value row was derived for a specific day/value.
-- Replace <USER_UUID> with the user you want to audit.

with params as (
  select
    '<USER_UUID>'::uuid as user_id,
    date '2025-02-25' as valuation_date,
    61463::numeric as expected_total_eur
),
portfolio_row as (
  select v.user_id, v.valuation_date, v.portfolio_value_eur
  from public.portfolio_daily_value v
  join params p
    on p.user_id = v.user_id
   and p.valuation_date = v.valuation_date
),
holdings as (
  select
    p.user_id,
    p.valuation_date,
    upper(trim(t.symbol)) as symbol,
    sum(
      case
        when t.side = 'BUY' then t.quantity::numeric
        when t.side = 'SELL' then -t.quantity::numeric
        else 0
      end
    ) as quantity
  from params p
  join public.transactions t
    on t.user_id = p.user_id
   and t.txn_date::date <= p.valuation_date
  group by p.user_id, p.valuation_date, upper(trim(t.symbol))
  having sum(
      case
        when t.side = 'BUY' then t.quantity::numeric
        when t.side = 'SELL' then -t.quantity::numeric
        else 0
      end
    ) > 0
),
latest_prices as (
  select
    h.user_id,
    h.valuation_date,
    h.symbol,
    h.quantity,
    pd.date as price_date,
    pd.close_native,
    pd.currency
  from holdings h
  left join lateral (
    select p.date, p.close_native, p.currency
    from public.prices_daily p
    where upper(trim(p.symbol)) = h.symbol
      and p.date <= h.valuation_date
    order by p.date desc
    limit 1
  ) pd on true
),
with_fx as (
  select
    lp.*,
    fx.date as fx_date,
    fx.eur_to_ccy,
    case
      when lp.currency = 'EUR' then 1::numeric
      when fx.eur_to_ccy is not null and fx.eur_to_ccy <> 0 then (1 / fx.eur_to_ccy)
      else null
    end as ccy_to_eur
  from latest_prices lp
  left join lateral (
    select f.date, f.eur_to_ccy
    from public.fx_daily f
    where f.ccy = lp.currency
      and f.date <= lp.valuation_date
    order by f.date desc
    limit 1
  ) fx on lp.currency <> 'EUR'
),
asset_values as (
  select
    wf.user_id,
    wf.valuation_date,
    wf.symbol,
    wf.quantity,
    wf.price_date,
    wf.close_native,
    wf.currency,
    wf.fx_date,
    wf.eur_to_ccy,
    wf.ccy_to_eur,
    (wf.quantity * wf.close_native) as value_native,
    (wf.quantity * wf.close_native * wf.ccy_to_eur) as value_eur
  from with_fx wf
)
select
  av.user_id,
  av.valuation_date,
  av.symbol,
  av.quantity,
  av.price_date,
  av.close_native,
  av.currency,
  av.fx_date,
  av.eur_to_ccy,
  av.ccy_to_eur,
  av.value_native,
  av.value_eur,
  pr.portfolio_value_eur as stored_portfolio_value_eur,
  p.expected_total_eur,
  sum(av.value_eur) over () as recomputed_total_eur,
  (sum(av.value_eur) over () - pr.portfolio_value_eur) as recomputed_minus_stored_eur,
  (sum(av.value_eur) over () - p.expected_total_eur) as recomputed_minus_expected_eur
from asset_values av
join params p
  on p.user_id = av.user_id
 and p.valuation_date = av.valuation_date
left join portfolio_row pr
  on pr.user_id = av.user_id
 and pr.valuation_date = av.valuation_date
order by av.value_eur desc nulls last, av.symbol;
