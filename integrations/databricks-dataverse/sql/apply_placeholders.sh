#!/usr/bin/env bash
# Substitute ${catalog} and ${pp_sp_app_id} then emit ordered SQL for Databricks.
# Usage:
#   ./apply_placeholders.sh my_catalog 00000000-0000-0000-0000-000000000000 > /tmp/crm_serve_bundle.sql
set -euo pipefail

CATALOG="${1:?catalog name required}"
PP_SP="${2:?Power Platform service principal app id required}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

for f in \
  00_schema.sql \
  01_account_order_summary.sql \
  02_account_open_invoices.sql \
  03_order_header_context.sql \
  04_order_line_context.sql \
  05_product_context.sql \
  06_uc_grants.sql \
  07_dim_crm_account.sql \
  08_refresh_mvs.sql
do
  echo "-- ===== ${f} ====="
  sed -e "s/\${catalog}/${CATALOG}/g" -e "s/\${pp_sp_app_id}/${PP_SP}/g" "${ROOT}/${f}"
  echo
done
