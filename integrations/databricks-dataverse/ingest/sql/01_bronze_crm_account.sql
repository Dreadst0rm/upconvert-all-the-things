-- Bronze landing for Dataverse Account export.
-- If Synapse Link already materializes Delta tables, CREATE OR REPLACE a view/table
-- that selects from the link location instead of re-copying.

CREATE SCHEMA IF NOT EXISTS ${catalog}.bronze;

CREATE TABLE IF NOT EXISTS ${catalog}.bronze.crm_account_raw (
  accountid STRING,
  name STRING,
  accountnumber STRING,
  new_erp_customer_id STRING,
  ownerid STRING,
  owneridname STRING,
  statuscode INT,
  statecode INT,
  modifiedon TIMESTAMP,
  sink_modified_on TIMESTAMP,
  _ingested_at TIMESTAMP
) USING DELTA
COMMENT 'Raw Dataverse Account from Synapse Link / Lakeflow Connect';

-- Example: register an external table over Synapse Link Delta path (adjust URI).
-- CREATE TABLE IF NOT EXISTS ${catalog}.bronze.crm_account_link
-- USING DELTA
-- LOCATION 'abfss://dataverse@linkstorage.dfs.core.windows.net/account';
--
-- Then refresh bronze with:
-- INSERT OVERWRITE ${catalog}.bronze.crm_account_raw
-- SELECT
--   accountid,
--   name,
--   accountnumber,
--   new_erp_customer_id,
--   ownerid,
--   owneridname,
--   statuscode,
--   statecode,
--   modifiedon,
--   SinkModifiedOn AS sink_modified_on,
--   current_timestamp() AS _ingested_at
-- FROM ${catalog}.bronze.crm_account_link;
