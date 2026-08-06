# Account form wiring

Wire model-driven Account forms to `crm_serve` virtual tables using the ERP bridge key.

## Form tabs (recommended)

| Tab | Control | Source VT | Filter |
|-----|---------|-----------|--------|
| Commerce | Summary fields / HTML web resource | `account_order_summary` | `customer_id = account.new_erp_customer_id` (single row) |
| Commerce | Subgrid: Open invoices | `account_open_invoices` | `customer_id eq ...` |
| Commerce | Subgrid: Recent orders | `order_header_context` | `customer_id eq ...` |
| Commerce | Subgrid: Order lines (optional) | `order_line_context` | `customer_id eq ...` **and** selected order |

## Subgrid filter template

In the subgrid **Edit filters** / related view:

```
customer_id Equals Account.new_erp_customer_id
```

If the relationship wizard cannot bind VT lookups cleanly, use a custom view with a fetchXML condition injected by form script (below).

## Form script (optional bridge when relationship is key-based)

Save as web resource `new_/scripts/account_crm_serve.js` and register on Account main form `OnLoad`:

```javascript
// Filter virtual-table subgrids by Account.new_erp_customer_id.
// Subgrid control names must match the form designer names below.
var SUBGRIDS = [
  "subgrid_open_invoices",
  "subgrid_recent_orders",
  "subgrid_order_lines"
];

function filterCrmServeSubgrids(executionContext) {
  var formContext = executionContext.getFormContext();
  var customerId = formContext.getAttribute("new_erp_customer_id")
    ? formContext.getAttribute("new_erp_customer_id").getValue()
    : null;

  if (!customerId) {
    return;
  }

  SUBGRIDS.forEach(function (gridName) {
    var grid = formContext.getControl(gridName);
    if (!grid || typeof grid.setFilterXml !== "function") {
      return;
    }
    // Attribute logical names on VTs follow the virtual table column schema names.
    var filter =
      "<filter type='and'>" +
      "<condition attribute='customer_id' operator='eq' value='" +
      customerId.replace(/'/g, "&apos;") +
      "' />" +
      "</filter>";
    grid.setFilterXml(filter);
    grid.refresh();
  });
}
```

Register: **Event** `OnLoad` → `filterCrmServeSubgrids` → pass execution context.

## Summary web resource (read-only KPI strip)

HTML web resource that calls the Dataverse Web API against the virtual table (example):

```html
<!DOCTYPE html>
<html>
  <body>
    <div id="kpi">Loading commerce summary…</div>
    <script>
      // Parent form passes account id via Xrm; look up VT by customer_id.
      // Prefer Web API: GET /api/data/v9.2/new_accountordersummaries?$filter=customer_id eq 'CUST-123'
      // Map fields: ltm_revenue, open_order_count, last_order_date, open_ar_balance, as_of_ts
    </script>
  </body>
</html>
```

Keep this read-only. Do not attempt to PATCH virtual tables for fact corrections.

## Relationship reminder

- Account (native) = 1-side.
- Virtual order/invoice tables = N-side via shared `customer_id` filter.
- Do not create 1:N with a virtual table as the primary (1) side.
