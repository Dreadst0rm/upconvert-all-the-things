# `crm_serve` contract

Stable API between Databricks gold and Dataverse virtual tables. Treat additive columns as non-breaking; renames/drops require coordinated VT recreate + managed solution release.

## Catalog assumptions

| Setting | Value | Notes |
|---------|-------|-------|
| Unity Catalog catalog | `${catalog}` | Placeholder; set per environment |
| Gold schema | `gold` | Existing star schema (facts + dims) |
| Serving schema | `crm_serve` | **Only** schema Dataverse binds to |
| Power Platform SP | `${pp_sp_app_id}` | Least-privilege SELECT on `crm_serve` |

Expected gold objects (adjust names in SQL if your warehouse differs):

| Object | Grain | Required keys |
|--------|-------|---------------|
| `gold.fact_order` | one row per order header | `order_sk`, `customer_sk`, `order_date`, `order_status`, `order_total` |
| `gold.fact_order_item` | one row per line | `order_item_sk`, `order_sk`, `product_sk`, `qty`, `line_amount` |
| `gold.fact_invoice` | one row per invoice | `invoice_sk`, `customer_sk`, `invoice_date`, `due_date`, `balance_due`, `invoice_status` |
| `gold.dim_customer` | one row per customer | `customer_sk`, `customer_id` (business key), `customer_name` |
| `gold.dim_product` | one row per product | `product_sk`, `product_id`, `product_name` |
| `gold.dim_crm_account` | optional CRM enrichment | `customer_id`, `accountid`, `owner_name` |

## Account bridge key

| Side | Field | Type | Purpose |
|------|-------|------|---------|
| Dataverse Account | `new_erp_customer_id` | Single line of text | Natural customer id from ERP / gold |
| Databricks | `customer_id` | STRING | Same natural key on dims and serving MVs |
| Databricks | `customer_sk` | BIGINT | Surrogate for joins inside the lake |

Matching rule: `account.new_erp_customer_id = crm_serve.*.customer_id` (exact string match after trim).

## Virtual-table PK rules

Every serving object must provide:

1. A primary key column of type **GUID (string)**, **BIGINT**, or **INT**.
2. At least one non-key **STRING** display field (`primary_name`).
3. A **materialized view or Delta table** (plain views are not supported as VT sources).

This contract standardizes on:

- Surrogate `*_sk` **BIGINT** as the Dataverse virtual-table primary key where a gold surrogate already exists.
- Deterministic `xxhash64`-based BIGINT keys only when no surrogate exists for a rolled-up grain.
- `primary_name` STRING for the VT primary name column.

Informational Unity Catalog `PRIMARY KEY` constraints are declared in SQL; uniqueness is enforced by the gold/serving pipeline.

## Serving objects

### 1. `crm_serve.account_order_summary`

| Property | Value |
|----------|-------|
| Grain | One row per `customer_id` |
| Refresh SLA | ≤ 1 hour |
| VT PK | `customer_sk` (BIGINT) |
| Primary name | `customer_name` |

| Column | Type | Description |
|--------|------|-------------|
| `customer_sk` | BIGINT | PK |
| `customer_id` | STRING | Bridge key to Account |
| `customer_name` | STRING | Display name |
| `ltm_revenue` | DECIMAL(18,2) | Last-12-month order total |
| `open_order_count` | INT | Orders in open statuses |
| `last_order_date` | DATE | Max order date |
| `open_ar_balance` | DECIMAL(18,2) | Sum of open invoice balances |
| `as_of_ts` | TIMESTAMP | Serving refresh watermark |

### 2. `crm_serve.account_open_invoices`

| Property | Value |
|----------|-------|
| Grain | One row per open invoice |
| Scope | `invoice_status` in open set **and** (`invoice_date` ≥ current_date − 24 months **or** `balance_due` > 0) |
| Refresh SLA | ≤ 1 hour |
| VT PK | `invoice_sk` (BIGINT) |
| Primary name | `invoice_number` |

| Column | Type | Description |
|--------|------|-------------|
| `invoice_sk` | BIGINT | PK |
| `invoice_number` | STRING | Display |
| `customer_sk` | BIGINT | Customer surrogate |
| `customer_id` | STRING | Bridge key |
| `customer_name` | STRING | Denormalized |
| `invoice_date` | DATE | |
| `due_date` | DATE | |
| `balance_due` | DECIMAL(18,2) | |
| `invoice_status` | STRING | |
| `as_of_ts` | TIMESTAMP | |

### 3. `crm_serve.order_header_context`

| Property | Value |
|----------|-------|
| Grain | One row per order header in window |
| Scope | Open status **or** `order_date` ≥ current_date − 90 days |
| Refresh SLA | ≤ 1 hour |
| VT PK | `order_sk` (BIGINT) |
| Primary name | `order_number` |

| Column | Type | Description |
|--------|------|-------------|
| `order_sk` | BIGINT | PK |
| `order_number` | STRING | Display |
| `customer_sk` | BIGINT | |
| `customer_id` | STRING | Bridge key |
| `customer_name` | STRING | |
| `order_date` | DATE | |
| `order_status` | STRING | |
| `order_total` | DECIMAL(18,2) | |
| `as_of_ts` | TIMESTAMP | |

### 4. `crm_serve.order_line_context`

| Property | Value |
|----------|-------|
| Grain | One row per line for headers in `order_header_context` |
| Refresh SLA | ≤ 1 hour |
| VT PK | `order_item_sk` (BIGINT) |
| Primary name | `line_label` |

| Column | Type | Description |
|--------|------|-------------|
| `order_item_sk` | BIGINT | PK |
| `line_label` | STRING | `order_number || ' / ' || product_id` |
| `order_sk` | BIGINT | Parent header |
| `order_number` | STRING | |
| `customer_id` | STRING | Bridge key |
| `product_sk` | BIGINT | |
| `product_id` | STRING | |
| `product_name` | STRING | |
| `qty` | DECIMAL(18,4) | |
| `line_amount` | DECIMAL(18,2) | |
| `as_of_ts` | TIMESTAMP | |

### 5. `crm_serve.product_context` (optional)

| Property | Value |
|----------|-------|
| Grain | One row per product referenced by `order_line_context` |
| Refresh SLA | ≤ 1 hour |
| VT PK | `product_sk` (BIGINT) |
| Primary name | `product_name` |

| Column | Type | Description |
|--------|------|-------------|
| `product_sk` | BIGINT | PK |
| `product_id` | STRING | |
| `product_name` | STRING | |
| `as_of_ts` | TIMESTAMP | |

## Refresh SLA summary

| Object | Target freshness | Mechanism |
|--------|------------------|-----------|
| All `crm_serve.*` MVs | ≤ 1 hour | Lakeflow / DLT schedule or `REFRESH MATERIALIZED VIEW` job |
| Gold facts feeding MVs | Per existing gold SLA | Unchanged |
| `dim_crm_account` | ≤ 4 hours after Dataverse change | Synapse Link / Lakeflow Connect → bronze → silver → gold |

## Row-count guardrails (VT)

Design targets so filtered Account form queries stay well under the ~1,000-row virtual-table ceiling:

| Object | Expected rows per account |
|--------|---------------------------|
| `account_order_summary` | 1 |
| `account_open_invoices` | typically < 200 |
| `order_header_context` | typically < 100 (90-day / open window) |
| `order_line_context` | typically < 500 for that window |

If an account exceeds these, tighten the window in SQL (do not page unbounded VTs in the app).

## Versioning

- Contract version: **1.0.0**
- Additive columns: bump **minor**, recreate VT columns via wizard “recreate” if needed.
- PK / grain / rename changes: bump **major**, new VT schema names preferred over in-place break.
