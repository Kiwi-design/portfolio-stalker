-- Reset txn_close_price values so backend refresh can re-resolve from market data.
-- Run this once, then open Transactions and click Refresh.

update transactions
set txn_close_price = null
where txn_close_price is null
   or btrim(txn_close_price) = ''
   or lower(btrim(txn_close_price)) = 'unavailable'
   or txn_close_price = to_char(price::numeric, 'FM9999999990.0000');
