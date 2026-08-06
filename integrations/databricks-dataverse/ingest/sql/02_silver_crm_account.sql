-- Silver: latest Account row per accountid with cleaned bridge key.

CREATE SCHEMA IF NOT EXISTS ${catalog}.silver;

CREATE OR REPLACE TABLE ${catalog}.silver.crm_account
USING DELTA
AS
WITH ranked AS (
  SELECT
    accountid,
    name,
    accountnumber,
    nullif(trim(new_erp_customer_id), '') AS customer_id,
    ownerid,
    owneridname,
    statuscode,
    statecode,
    modifiedon,
    sink_modified_on,
    _ingested_at,
    row_number() OVER (
      PARTITION BY accountid
      ORDER BY coalesce(sink_modified_on, modifiedon, _ingested_at) DESC
    ) AS rn
  FROM ${catalog}.bronze.crm_account_raw
  WHERE accountid IS NOT NULL
)
SELECT
  accountid,
  name AS account_name,
  accountnumber AS account_number,
  customer_id,
  ownerid AS owner_id,
  owneridname AS owner_name,
  statuscode,
  statecode,
  modifiedon,
  current_timestamp() AS as_of_ts
FROM ranked
WHERE rn = 1;
