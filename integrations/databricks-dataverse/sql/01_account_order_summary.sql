-- Persona mart: one row per customer for Account form header context.
-- VT PK: customer_sk (BIGINT). Primary name: customer_name.

CREATE OR REPLACE MATERIALIZED VIEW ${catalog}.crm_serve.account_order_summary
(
  customer_sk BIGINT NOT NULL,
  customer_id STRING NOT NULL,
  customer_name STRING NOT NULL,
  ltm_revenue DECIMAL(18, 2),
  open_order_count INT,
  last_order_date DATE,
  open_ar_balance DECIMAL(18, 2),
  as_of_ts TIMESTAMP,
  CONSTRAINT pk_account_order_summary PRIMARY KEY (customer_sk)
)
COMMENT 'CRM serve: account order / AR summary (grain = customer_id)'
AS
WITH open_orders AS (
  SELECT o.customer_sk,
         COUNT(*) AS open_order_count
  FROM ${catalog}.gold.fact_order o
  INNER JOIN ${catalog}.crm_serve._config_open_order_status s
    ON o.order_status = s.order_status
  GROUP BY o.customer_sk
),
ltm AS (
  SELECT customer_sk,
         CAST(SUM(order_total) AS DECIMAL(18, 2)) AS ltm_revenue,
         MAX(order_date) AS last_order_date
  FROM ${catalog}.gold.fact_order
  WHERE order_date >= date_add(current_date(), -365)
  GROUP BY customer_sk
),
ar AS (
  SELECT i.customer_sk,
         CAST(SUM(i.balance_due) AS DECIMAL(18, 2)) AS open_ar_balance
  FROM ${catalog}.gold.fact_invoice i
  INNER JOIN ${catalog}.crm_serve._config_open_invoice_status s
    ON i.invoice_status = s.invoice_status
  WHERE i.balance_due > 0
  GROUP BY i.customer_sk
)
SELECT
  c.customer_sk,
  c.customer_id,
  c.customer_name,
  COALESCE(ltm.ltm_revenue, CAST(0 AS DECIMAL(18, 2))) AS ltm_revenue,
  COALESCE(oo.open_order_count, 0) AS open_order_count,
  ltm.last_order_date,
  COALESCE(ar.open_ar_balance, CAST(0 AS DECIMAL(18, 2))) AS open_ar_balance,
  current_timestamp() AS as_of_ts
FROM ${catalog}.gold.dim_customer c
LEFT JOIN ltm ON c.customer_sk = ltm.customer_sk
LEFT JOIN open_orders oo ON c.customer_sk = oo.customer_sk
LEFT JOIN ar ON c.customer_sk = ar.customer_sk
WHERE c.customer_id IS NOT NULL;
