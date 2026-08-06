-- Scheduled refresh for crm_serve materialized views.
-- Run from a Databricks Job (SQL task) every hour (matches CONTRACT SLA).

REFRESH MATERIALIZED VIEW ${catalog}.crm_serve.account_order_summary;
REFRESH MATERIALIZED VIEW ${catalog}.crm_serve.account_open_invoices;
REFRESH MATERIALIZED VIEW ${catalog}.crm_serve.order_header_context;
REFRESH MATERIALIZED VIEW ${catalog}.crm_serve.order_line_context;
REFRESH MATERIALIZED VIEW ${catalog}.crm_serve.product_context;
