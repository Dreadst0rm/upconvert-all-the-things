-- Open invoices scoped for CRM Account subgrids (24-month / open balance).
-- VT PK: invoice_sk (BIGINT). Primary name: invoice_number.

CREATE OR REPLACE MATERIALIZED VIEW ${catalog}.crm_serve.account_open_invoices
(
  invoice_sk BIGINT NOT NULL,
  invoice_number STRING NOT NULL,
  customer_sk BIGINT NOT NULL,
  customer_id STRING NOT NULL,
  customer_name STRING NOT NULL,
  invoice_date DATE,
  due_date DATE,
  balance_due DECIMAL(18, 2),
  invoice_status STRING,
  as_of_ts TIMESTAMP,
  CONSTRAINT pk_account_open_invoices PRIMARY KEY (invoice_sk)
)
COMMENT 'CRM serve: open invoices for Account forms (filtered window)'
AS
SELECT
  i.invoice_sk,
  COALESCE(i.invoice_number, CAST(i.invoice_sk AS STRING)) AS invoice_number,
  c.customer_sk,
  c.customer_id,
  c.customer_name,
  i.invoice_date,
  i.due_date,
  CAST(i.balance_due AS DECIMAL(18, 2)) AS balance_due,
  i.invoice_status,
  current_timestamp() AS as_of_ts
FROM ${catalog}.gold.fact_invoice i
INNER JOIN ${catalog}.gold.dim_customer c
  ON i.customer_sk = c.customer_sk
INNER JOIN ${catalog}.crm_serve._config_open_invoice_status s
  ON i.invoice_status = s.invoice_status
WHERE c.customer_id IS NOT NULL
  AND (
    i.balance_due > 0
    OR i.invoice_date >= date_add(current_date(), -730)
  );
