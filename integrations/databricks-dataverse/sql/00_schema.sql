-- crm_serve schema bootstrap
-- Replace ${catalog} before apply, or SET a widget / pipeline param.

CREATE SCHEMA IF NOT EXISTS ${catalog}.crm_serve
COMMENT 'CRM serving contract for Dataverse virtual tables. Bind Dataverse only to this schema.';

-- Open-status reference lists (adjust to your gold status codes).
-- Prefer keeping these in a small config table if statuses vary by brand/region.
CREATE TABLE IF NOT EXISTS ${catalog}.crm_serve._config_open_order_status (
  order_status STRING NOT NULL,
  CONSTRAINT pk_open_order_status PRIMARY KEY (order_status)
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${catalog}.crm_serve._config_open_invoice_status (
  invoice_status STRING NOT NULL,
  CONSTRAINT pk_open_invoice_status PRIMARY KEY (invoice_status)
) USING DELTA;

-- Seed defaults (idempotent merges).
MERGE INTO ${catalog}.crm_serve._config_open_order_status AS t
USING (
  SELECT explode(array('OPEN', 'PENDING', 'IN_PROGRESS', 'BACKORDER')) AS order_status
) AS s
ON t.order_status = s.order_status
WHEN NOT MATCHED THEN INSERT (order_status) VALUES (s.order_status);

MERGE INTO ${catalog}.crm_serve._config_open_invoice_status AS t
USING (
  SELECT explode(array('OPEN', 'PARTIAL', 'OVERDUE')) AS invoice_status
) AS s
ON t.invoice_status = s.invoice_status
WHEN NOT MATCHED THEN INSERT (invoice_status) VALUES (s.invoice_status);
