-- Lines only for orders present in order_header_context (narrow window).
-- VT PK: order_item_sk (BIGINT). Primary name: line_label.

CREATE OR REPLACE MATERIALIZED VIEW ${catalog}.crm_serve.order_line_context
(
  order_item_sk BIGINT NOT NULL,
  line_label STRING NOT NULL,
  order_sk BIGINT NOT NULL,
  order_number STRING NOT NULL,
  customer_id STRING NOT NULL,
  product_sk BIGINT,
  product_id STRING,
  product_name STRING,
  qty DECIMAL(18, 4),
  line_amount DECIMAL(18, 2),
  as_of_ts TIMESTAMP,
  CONSTRAINT pk_order_line_context PRIMARY KEY (order_item_sk)
)
COMMENT 'CRM serve: order lines for header context set only'
AS
SELECT
  li.order_item_sk,
  concat_ws(' / ', h.order_number, COALESCE(p.product_id, CAST(li.product_sk AS STRING))) AS line_label,
  h.order_sk,
  h.order_number,
  h.customer_id,
  li.product_sk,
  p.product_id,
  p.product_name,
  CAST(li.qty AS DECIMAL(18, 4)) AS qty,
  CAST(li.line_amount AS DECIMAL(18, 2)) AS line_amount,
  current_timestamp() AS as_of_ts
FROM ${catalog}.gold.fact_order_item li
INNER JOIN ${catalog}.crm_serve.order_header_context h
  ON li.order_sk = h.order_sk
LEFT JOIN ${catalog}.gold.dim_product p
  ON li.product_sk = p.product_sk;
