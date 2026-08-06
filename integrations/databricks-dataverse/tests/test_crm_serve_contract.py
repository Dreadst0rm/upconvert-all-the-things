"""Validate crm_serve contract artifacts without a live Databricks workspace."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
CONTRACT = (ROOT / "docs" / "CONTRACT.md").read_text(encoding="utf-8")

REQUIRED_OBJECTS = [
    "account_order_summary",
    "account_open_invoices",
    "order_header_context",
    "order_line_context",
    "product_context",
]

REQUIRED_SQL_FILES = [
    "00_schema.sql",
    "01_account_order_summary.sql",
    "02_account_open_invoices.sql",
    "03_order_header_context.sql",
    "04_order_line_context.sql",
    "05_product_context.sql",
    "06_uc_grants.sql",
    "07_dim_crm_account.sql",
    "08_refresh_mvs.sql",
]


def test_sql_files_exist() -> None:
    missing = [name for name in REQUIRED_SQL_FILES if not (SQL_DIR / name).exists()]
    assert not missing, f"Missing SQL files: {missing}"


def test_each_serving_object_has_materialized_view_and_pk() -> None:
    for obj in REQUIRED_OBJECTS:
        matches = list(SQL_DIR.glob(f"*_{obj}.sql"))
        assert matches, f"No SQL file for {obj}"
        text = matches[0].read_text(encoding="utf-8")
        assert "MATERIALIZED VIEW" in text, f"{obj} must be a materialized view"
        assert "PRIMARY KEY" in text, f"{obj} must declare a PRIMARY KEY"
        assert "primary_name" in CONTRACT.lower() or "Primary name" in CONTRACT
        assert f"crm_serve.{obj}" in text or f"crm_serve.{obj}" in CONTRACT


def test_grants_are_select_only_on_crm_serve() -> None:
    grants = (SQL_DIR / "06_uc_grants.sql").read_text(encoding="utf-8")
    assert "GRANT SELECT" in grants
    assert "crm_serve" in grants
    assert "GRANT MODIFY" not in grants
    assert "gold." not in grants or "Do NOT grant SELECT on gold" in grants


def test_contract_documents_bridge_key_and_sla() -> None:
    assert "new_erp_customer_id" in CONTRACT
    assert "customer_id" in CONTRACT
    assert "≤ 1 hour" in CONTRACT or "<= 1 hour" in CONTRACT


def test_placeholders_present_for_env_substitution() -> None:
    schema = (SQL_DIR / "00_schema.sql").read_text(encoding="utf-8")
    assert "${catalog}" in schema
    grants = (SQL_DIR / "06_uc_grants.sql").read_text(encoding="utf-8")
    assert "${pp_sp_app_id}" in grants


def test_no_plain_view_as_vt_source_for_core_objects() -> None:
    """Core VT sources must be MVs; plain CREATE VIEW is only allowed for enrichment helpers."""
    for path in SQL_DIR.glob("0[1-5]_*.sql"):
        text = path.read_text(encoding="utf-8")
        # Allow CREATE OR REPLACE MATERIALIZED VIEW only as the object definition.
        assert re.search(r"CREATE OR REPLACE MATERIALIZED VIEW", text), path.name
        assert not re.search(r"CREATE OR REPLACE VIEW\s+\$\{catalog\}\.crm_serve\.(account_|order_|product_)", text)


if __name__ == "__main__":
    test_sql_files_exist()
    test_each_serving_object_has_materialized_view_and_pk()
    test_grants_are_select_only_on_crm_serve()
    test_contract_documents_bridge_key_and_sla()
    test_placeholders_present_for_env_substitution()
    test_no_plain_view_as_vt_source_for_core_objects()
    print("crm_serve contract tests OK")
