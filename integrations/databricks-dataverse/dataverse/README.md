# Dataverse binding guide

Create Azure Databricks virtual tables against `crm_serve` only. Wire Account forms with the ERP bridge key.

## Prerequisites

- `crm_serve` MVs refreshed and granted to the Power Platform service principal ([../sql/06_uc_grants.sql](../sql/06_uc_grants.sql)).
- System Customizer or System Administrator in the target Dataverse environment.
- Virtual Connector Provider solution up to date in the environment.

## 1. Entra app + Databricks connection

1. Register an Entra ID application (service principal) for Power Platform → Databricks.
2. In Databricks, create the SP as a user/service principal and apply `06_uc_grants.sql`.
3. In Power Apps → **Connections** → **Azure Databricks**:
   - Auth: service principal (client id / secret / tenant).
   - Host: workspace URL.
   - HTTP path: SQL warehouse HTTP path (serverless or classic warehouse dedicated to CRM reads).
4. Share the connection with the **Virtual Connector Provider** application if prompted after recreate.

Reference: [Create an Azure Databricks connection on Microsoft Power Platform](https://learn.microsoft.com/en-us/azure/databricks/integrations/msft-power-platform/setup).

## 2. Create virtual tables

For each object in order:

1. `account_order_summary`
2. `account_open_invoices`
3. `order_header_context`
4. `order_line_context`
5. (optional) `product_context`

Steps (Power Apps → Solutions → your managed solution):

1. **New** → **Table** → **Virtual table**.
2. Select the Azure Databricks connection.
3. Choose catalog → `crm_serve` → table/MV.
4. Confirm PK (BIGINT `*_sk`) and primary name (string display field).
5. Set publisher-prefixed schema names, e.g.:
   - Display: `Account Order Summary`
   - Schema: `new_accountordersummary`
6. Finish and verify rows load in the table designer.

**Do not** bind plain SQL views. **Do not** bind `gold.*` facts.

ALM: include virtual tables + connection reference in a managed solution. Prefer environment variables for connection details where supported.

## 3. Account bridge field

Add to **Account** (native):

| Display name | Schema name | Type | Required |
|--------------|-------------|------|----------|
| ERP Customer Id | `new_erp_customer_id` | Single line of text (100) | Business-required for synced accounts |

Populate via:

- Dual-write / integration from ERP master, or
- Periodic Power Automate / Dataflow matching Account Number → `customer_id`, or
- Manual data steward process for pilot accounts.

See [account_bridge_field.md](account_bridge_field.md) for field metadata and view columns.

## 4. Account form wiring

See [form_wiring.md](form_wiring.md) for subgrid filters and a summary web-resource pattern.

Rules of thumb:

- Native Account is the 1-side; never put a virtual table on the 1-side of 1:N.
- Every subgrid **must** filter `customer_id eq {account.new_erp_customer_id}`.
- Prefer summary + open invoices + recent orders on the form; deep history stays in Power BI.

## 5. Security roles

| Role | Native | Virtual tables |
|------|--------|----------------|
| Sales persona | Account R/W as today | Read on summary + open invoices + order header |
| Finance persona | Account R | Read on summary + open invoices |
| Maker / admin | Full | Full on all `crm_serve` VTs |

Remember: real row security is Unity Catalog on the SP connection. Keep serving MVs persona-safe by construction.
