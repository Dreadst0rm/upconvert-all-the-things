# Account bridge field (`new_erp_customer_id`)

## Purpose

Join native Dataverse **Account** rows to Databricks `crm_serve.*.customer_id` without copying facts into Dataverse.

## Field definition

```xml
<!-- Conceptual Attribute metadata for solution packaging.
     Create via maker portal or include in an unmanaged solution export. -->
<attribute PhysicalName="new_erp_customer_id">
  <Type>nvarchar</Type>
  <Name>new_erp_customer_id</Name>
  <LogicalName>new_erp_customer_id</LogicalName>
  <RequiredLevel>recommended</RequiredLevel>
  <DisplayName>ERP Customer Id</DisplayName>
  <Description>Natural customer key matching Databricks gold.dim_customer.customer_id</Description>
  <MaxLength>100</MaxLength>
  <IsValidForCreate>1</IsValidForCreate>
  <IsValidForUpdate>1</IsValidForUpdate>
  <IsValidForRead>1</IsValidForRead>
</attribute>
```

## Publisher

Use your solution publisher prefix instead of `new_` if different. Update:

- This file
- [form_wiring.md](form_wiring.md)
- [../docs/CONTRACT.md](../docs/CONTRACT.md)
- Power Automate parameter names in [../power-automate/](../power-automate/)

## Population checklist

1. Identify source of truth for customer natural key (ERP / MDM).
2. Backfill existing Accounts where the key is known.
3. Add the column to Account quick-find / main views for data stewards.
4. Reject CRM workflows that depend on lake context when the field is empty (fail closed).

## Matching SQL (Databricks QA)

```sql
-- Orphans: Accounts in dim_crm_account with no gold customer
SELECT d.*
FROM ${catalog}.gold.dim_crm_account d
LEFT JOIN ${catalog}.gold.dim_customer c
  ON d.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- Orphans: gold customers with CRM account but missing from serving summary
SELECT c.customer_id
FROM ${catalog}.gold.dim_customer c
INNER JOIN ${catalog}.gold.dim_crm_account d
  ON c.customer_id = d.customer_id
LEFT JOIN ${catalog}.crm_serve.account_order_summary s
  ON c.customer_id = s.customer_id
WHERE s.customer_id IS NULL;
```
