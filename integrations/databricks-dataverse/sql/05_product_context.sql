-- Optional product context for lines in the CRM window.
-- VT PK: product_sk (BIGINT). Primary name: product_name.

CREATE OR REPLACE MATERIALIZED VIEW ${catalog}.crm_serve.product_context
(
  product_sk BIGINT NOT NULL,
  product_id STRING NOT NULL,
  product_name STRING NOT NULL,
  as_of_ts TIMESTAMP,
  CONSTRAINT pk_product_context PRIMARY KEY (product_sk)
)
COMMENT 'CRM serve: products referenced by order_line_context'
AS
SELECT DISTINCT
  p.product_sk,
  p.product_id,
  p.product_name,
  current_timestamp() AS as_of_ts
FROM ${catalog}.gold.dim_product p
INNER JOIN ${catalog}.crm_serve.order_line_context l
  ON p.product_sk = l.product_sk
WHERE p.product_id IS NOT NULL
  AND p.product_name IS NOT NULL;
