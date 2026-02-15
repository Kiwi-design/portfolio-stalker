-- Force existing transactions to be re-resolved by /api/isin_name sync.
-- Run this once in Supabase SQL Editor, then trigger Transactions -> Refresh in the app.

update public.transactions
set txn_close_price = null
where txn_date is not null
  and (
    txn_close_price is null
    or btrim(txn_close_price) = ''
    or lower(btrim(txn_close_price)) = 'unavailable'
    or txn_close_price !~ '\\s[A-Z]{3}$'
  );
