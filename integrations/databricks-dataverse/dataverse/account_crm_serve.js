/**
 * Filter virtual-table subgrids by Account.new_erp_customer_id.
 * Register on Account main form OnLoad; pass execution context as first parameter.
 * Update SUBGRIDS to match form control names; update attribute logical names to your VT schema.
 */
var SUBGRIDS = [
  "subgrid_open_invoices",
  "subgrid_recent_orders",
  "subgrid_order_lines"
];

function filterCrmServeSubgrids(executionContext) {
  var formContext = executionContext.getFormContext();
  var attr = formContext.getAttribute("new_erp_customer_id");
  var customerId = attr ? attr.getValue() : null;

  if (!customerId) {
    return;
  }

  var safe = String(customerId).replace(/&/g, "&amp;").replace(/'/g, "&apos;");

  SUBGRIDS.forEach(function (gridName) {
    var grid = formContext.getControl(gridName);
    if (!grid || typeof grid.setFilterXml !== "function") {
      return;
    }
    var filter =
      "<filter type='and'>" +
      "<condition attribute='customer_id' operator='eq' value='" +
      safe +
      "' />" +
      "</filter>";
    grid.setFilterXml(filter);
    grid.refresh();
  });
}
