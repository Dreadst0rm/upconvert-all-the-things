"""Additional package integrity checks for flows and ingest."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reference_flow_forbids_databricks_writes() -> None:
    path = ROOT / "power-automate" / "open_ar_threshold_task.definition.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pattern"] == "crm_serve_read_native_write"
    assert data["constraints"]["allowedWriteEntities"] == ["tasks"]
    assert any("Merge" in x or "Write" in x for x in data["constraints"]["forbiddenActions"])
    # Ensure create targets tasks only in the definition text
    raw = path.read_text(encoding="utf-8")
    assert '"entityName": "tasks"' in raw
    assert "NATIVE WRITE ONLY" in raw


def test_ingest_sql_chain_exists() -> None:
    ingest = ROOT / "ingest" / "sql"
    for name in (
        "01_bronze_crm_account.sql",
        "02_silver_crm_account.sql",
        "03_merge_dim_crm_account.sql",
    ):
        assert (ingest / name).exists(), name
    merge = (ingest / "03_merge_dim_crm_account.sql").read_text(encoding="utf-8")
    assert "MERGE INTO ${catalog}.gold.dim_crm_account" in merge
    assert "customer_id" in merge


def test_dataverse_form_script_filters_bridge_key() -> None:
    js = (ROOT / "dataverse" / "account_crm_serve.js").read_text(encoding="utf-8")
    assert "new_erp_customer_id" in js
    assert "setFilterXml" in js
    assert "customer_id" in js


if __name__ == "__main__":
    test_reference_flow_forbids_databricks_writes()
    test_ingest_sql_chain_exists()
    test_dataverse_form_script_filters_bridge_key()
    print("flow/ingest/dataverse tests OK")
