-- Backfill txn_close_price for existing rows that are empty/unavailable.
-- Safe fallback: use the transaction input price (EUR) when close lookup was not resolved.

update transactions
set txn_close_price = to_char(price::numeric, 'FM9999999990.0000')
where txn_close_price is null
   or btrim(txn_close_price) = ''
   or lower(btrim(txn_close_price)) = 'unavailable';
