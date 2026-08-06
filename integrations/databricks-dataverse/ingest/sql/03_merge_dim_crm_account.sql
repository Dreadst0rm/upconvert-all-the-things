-- Gold dim: grain = customer_id (ERP bridge). One CRM account per customer_id.
-- Requires ${catalog}.gold.dim_crm_account from sql/07_dim_crm_account.sql.

MERGE INTO ${catalog}.gold.dim_crm_account AS t
USING (
  SELECT
    customer_id,
    accountid,
    account_name,
    owner_name,
    owner_id,
    account_number,
    statuscode,
    statecode,
    modifiedon,
    as_of_ts
  FROM (
    SELECT
      s.*,
      row_number() OVER (
        PARTITION BY customer_id
        ORDER BY coalesce(modifiedon, as_of_ts) DESC
      ) AS rn
    FROM ${catalog}.silver.crm_account s
    WHERE customer_id IS NOT NULL
  )
  WHERE rn = 1
) AS s
ON t.customer_id = s.customer_id
WHEN MATCHED THEN UPDATE SET
  t.accountid = s.accountid,
  t.account_name = s.account_name,
  t.owner_name = s.owner_name,
  t.owner_id = s.owner_id,
  t.account_number = s.account_number,
  t.statuscode = s.statuscode,
  t.statecode = s.statecode,
  t.modifiedon = s.modifiedon,
  t.as_of_ts = s.as_of_ts
WHEN NOT MATCHED THEN INSERT (
  customer_id,
  accountid,
  account_name,
  owner_name,
  owner_id,
  account_number,
  statuscode,
  statecode,
  modifiedon,
  as_of_ts
) VALUES (
  s.customer_id,
  s.accountid,
  s.account_name,
  s.owner_name,
  s.owner_id,
  s.account_number,
  s.statuscode,
  s.statecode,
  s.modifiedon,
  s.as_of_ts
);
