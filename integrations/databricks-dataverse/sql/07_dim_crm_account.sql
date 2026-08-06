-- Optional gold dimension enriched from Dataverse Account (after ingest pipeline).
-- Apply after bronze/silver CRM account land — see ../ingest/README.md.

CREATE TABLE IF NOT EXISTS ${catalog}.gold.dim_crm_account (
  customer_id STRING NOT NULL COMMENT 'Matches gold.dim_customer.customer_id / Account.new_erp_customer_id',
  accountid STRING NOT NULL COMMENT 'Dataverse Account GUID',
  account_name STRING,
  owner_name STRING,
  owner_id STRING,
  account_number STRING,
  statuscode INT,
  statecode INT,
  modifiedon TIMESTAMP,
  as_of_ts TIMESTAMP,
  CONSTRAINT pk_dim_crm_account PRIMARY KEY (customer_id)
) USING DELTA
COMMENT 'CRM Account attributes joined into serving MVs when present';

-- Example enrichment view used by makers/BI (not a VT source unless materialized separately).
CREATE OR REPLACE VIEW ${catalog}.crm_serve.v_account_order_summary_enriched
AS
SELECT
  s.*,
  d.accountid AS dataverse_account_id,
  d.owner_name AS crm_owner_name,
  d.statuscode AS crm_statuscode
FROM ${catalog}.crm_serve.account_order_summary s
LEFT JOIN ${catalog}.gold.dim_crm_account d
  ON s.customer_id = d.customer_id;
