# Databricks gold → Dataverse CRM serving

Zero-copy pattern: keep order / item / invoice truth in Databricks gold, publish a thin `crm_serve` contract as materialized views, and project those into Dataverse as **virtual tables**. Native Dataverse holds CRM operational state only. Power Automate reads lake context and writes **only** native CRM entities.

## Layout

| Path | Purpose |
|------|---------|
| [docs/CONTRACT.md](docs/CONTRACT.md) | Serving API: objects, PKs, Account bridge key, refresh SLAs |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Ownership split, anti-patterns, persona strategy |
| [sql/](sql/) | Unity Catalog schema, MVs, grants |
| [dataverse/](dataverse/) | SP connection, virtual tables, Account form wiring |
| [power-automate/](power-automate/) | Reference flow: open-AR threshold → Task |
| [ingest/](ingest/) | Dataverse → Databricks bronze/silver/gold CRM dims |
| [tests/](tests/) | Contract validation helpers |

## Quick start

1. Apply SQL in order (`00` → `07`) against a Unity Catalog catalog that already has gold stars.
2. Grant the Power Platform service principal on `crm_serve` only (`06_uc_grants.sql`).
3. Follow [dataverse/README.md](dataverse/README.md) to create the Azure Databricks connection and virtual tables.
4. Import the reference flow from [power-automate/](power-automate/).
5. Stand up CRM → lake ingest per [ingest/README.md](ingest/README.md).

## Locked decisions

- Access mode: read CRM context + flows that mutate **native** CRM only (no lake fact write-back).
- Serving path: Azure Databricks virtual connector (no Fabric required).
