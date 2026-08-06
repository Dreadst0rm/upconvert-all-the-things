-- Least-privilege Unity Catalog grants for the Power Platform service principal.
-- Replace ${catalog} and ${pp_sp_app_id} (Entra application / service principal id).
-- Databricks principal name is typically: `${pp_sp_app_id}` or a group wrapping it.

-- USAGE on catalog + schema
GRANT USE CATALOG ON CATALOG ${catalog} TO `${pp_sp_app_id}`;
GRANT USE SCHEMA ON SCHEMA ${catalog}.crm_serve TO `${pp_sp_app_id}`;

-- Read only the serving contract (not raw gold)
GRANT SELECT ON TABLE ${catalog}.crm_serve.account_order_summary TO `${pp_sp_app_id}`;
GRANT SELECT ON TABLE ${catalog}.crm_serve.account_open_invoices TO `${pp_sp_app_id}`;
GRANT SELECT ON TABLE ${catalog}.crm_serve.order_header_context TO `${pp_sp_app_id}`;
GRANT SELECT ON TABLE ${catalog}.crm_serve.order_line_context TO `${pp_sp_app_id}`;
GRANT SELECT ON TABLE ${catalog}.crm_serve.product_context TO `${pp_sp_app_id}`;

-- Do NOT grant SELECT on gold.* or bronze/silver to the Power Platform SP.
-- Config tables are internal; omit SELECT unless makers need to debug statuses.

-- Optional: future persona row filters belong on these MVs / a dedicated persona schema,
-- not on Dataverse security roles alone (VT does not provide full Dataverse RLS).
