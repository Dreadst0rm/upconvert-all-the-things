# Power Automate — open AR threshold → Task

Reference flow for access mode **1B**: read lake/CRM serving context, write **only** native Dataverse entities.

## Intent

When an Account’s `open_ar_balance` from `crm_serve.account_order_summary` exceeds a threshold, create a native **Task** (and optionally stamp an Opportunity risk flag). Never update Databricks facts.

## Parameters

| Name | Default | Description |
|------|---------|-------------|
| `OpenArThreshold` | `10000` | Currency threshold |
| `TaskSubjectPrefix` | `Open AR review` | Task subject prefix |
| `ErpCustomerField` | `new_erp_customer_id` | Account bridge attribute |

## Flow outline

1. **Trigger:** Recurrence (daily) **or** manual/button on Account form.
2. **List rows** Accounts where `new_erp_customer_id` is not null.
3. **For each Account:**
   - **List rows** virtual table `account_order_summary` filtered by `customer_id eq '{new_erp_customer_id}'` (top 1).
   - **Condition:** `open_ar_balance` ≥ threshold.
   - **Create row** Task:
     - `subject` = `{prefix}: {account.name} ({open_ar_balance})`
     - `regardingobjectid` = Account
     - `description` = include `ltm_revenue`, `open_order_count`, `last_order_date`, `as_of_ts`
   - **Do not** call Databricks MERGE/UPDATE/INSERT against gold or `crm_serve`.

## Import

1. Create an empty cloud flow in the target environment.
2. Use [open_ar_threshold_task.definition.json](open_ar_threshold_task.definition.json) as the working definition — paste actions into the designer or adapt via Solutions + unpack tooling.
3. Bind connections:
   - Microsoft Dataverse (current environment)
4. Set threshold in the Compose action `OpenArThreshold`.
5. Confirm virtual table set name (`new_accountordersummaries` or your plural schema name) matches the environment.

## Acceptance checks

- [ ] Flow succeeds when Account has bridge key and summary row.
- [ ] Task is created on native `tasks` only.
- [ ] No Databricks write actions exist in the flow.
- [ ] Empty bridge key → skip (no task).
- [ ] Below threshold → skip.

## Alternative: Databricks SQL action (read-only)

For heavier logic, use Azure Databricks **Execute a SQL Statement** against `crm_serve.account_order_summary` with a warehouse id, then create the Task in Dataverse. Still no fact write-back.
