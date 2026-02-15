-- Normalize existing NULL/blank txn_close_price so UI/backfill pipeline can process consistently.
-- This script does NOT copy transaction input price into txn_close_price.

update transactions
set txn_close_price = 'unavailable'
where txn_close_price is null
   or btrim(txn_close_price) = '';
