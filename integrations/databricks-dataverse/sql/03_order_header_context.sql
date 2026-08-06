-- Recent / open order headers for CRM context (not full history).
-- VT PK: order_sk (BIGINT). Primary name: order_number.

CREATE OR REPLACE MATERIALIZED VIEW ${catalog}.crm_serve.order_header_context
(
  order_sk BIGINT NOT NULL,
  order_number STRING NOT NULL,
  customer_sk BIGINT NOT NULL,
  customer_id STRING NOT NULL,
  customer_name STRING NOT NULL,
  order_date DATE,
  order_status STRING,
  order_total DECIMAL(18, 2),
  as_of_ts TIMESTAMP,
  CONSTRAINT pk_order_header_context PRIMARY KEY (order_sk)
)
COMMENT 'CRM serve: open or last-90-day order headers'
AS
SELECT
  o.order_sk,
  COALESCE(o.order_number, CAST(o.order_sk AS STRING)) AS order_number,
  c.customer_sk,
  c.customer_id,
  c.customer_name,
  o.order_date,
  o.order_status,
  CAST(o.order_total AS DECIMAL(18, 2)) AS order_total,
  current_timestamp() AS as_of_ts
FROM ${catalog}.gold.fact_order o
INNER JOIN ${catalog}.gold.dim_customer c
  ON o.customer_sk = c.customer_sk
LEFT JOIN ${catalog}.crm_serve._config_open_order_status s
  ON o.order_status = s.order_status
WHERE c.customer_id IS NOT NULL
  AND (
    s.order_status IS NOT NULL
    OR o.order_date >= date_add(current_date(), -90)
  );
