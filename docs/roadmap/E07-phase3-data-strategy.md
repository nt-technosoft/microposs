# E07 Phase 3 — Data Reset and Rebuild Strategy

> **Reference / data-safety context.**
>
> This document records backup/reset decisions from the earlier E07 cycle.
> It remains valid for data safety, but it is not the active implementation
> roadmap.
>
> Active entrypoint: [`E07-procurement-workspace.md`](./E07-procurement-workspace.md).
> Active reset plan: [`E07-controlled-radical-reset.md`](./E07-controlled-radical-reset.md).
>
> Excel workflow updates are intentionally postponed until the new backend core
> is stable.

## Decision

For E07 local/dev work, we choose **dev reset + staged rebuild**, not migration
of current experimental procurement data.

Reason:

- current procurement data was created against old mixed semantics;
- E07 changes funding, settlement, payment and receive boundaries;
- migrating old local drafts would preserve polluted assumptions;
- a verified DB dump already exists before the rework;
- canonical Excel workflow is the right source for realistic replay.

## Backup

Current filled local DB was preserved before E07 rework:

```text
backups/microposs_before_procurement_rearchitecture_20260513_001544.dump
```

Do not delete this dump during E07.

Before the clean schema reset, an additional fresh dump was created:

```text
backups/microposs_before_clean_schema_reset_20260513_054651.dump
```

## Reset Boundary

Reset is allowed only for local/dev data after explicit user confirmation.

Do not reset automatically from an agent task unless the user explicitly asks to
clean the database in that turn.

Production/stage data must not use this flow.

## What We Keep

Durable project assets:

- source code;
- migrations;
- roadmap/domain docs;
- Excel source file;
- JSON import snapshot;
- DB backup dump.

Business data in the current local DB is disposable after backup.

## What We Rebuild

After reset, rebuild data through domain services/API-like flows only:

- users and business tenant;
- warehouses and cash accounts;
- investors/operators;
- suppliers;
- products and variants;
- investment agreement or partnership procurement;
- capital contributions and allocations;
- own-funds procurement payment from `CashAccount`;
- supplier settlement scenarios;
- partial receives with batch snapshots;
- stock transfers;
- POS sessions and sales;
- reports/audit verification.

## Canonical Rebuild Path

Primary path:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage baseline --apply --wipe

DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage procurements --apply

DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage transfers --apply

DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage sales --apply

DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage final --apply
```

Fast audit path after staged flow is trusted:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_audit --apply --wipe
```

Dry-run before destructive apply:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_audit --dry-run
```

## Required E07 Updates Before Final Rebuild

Do not start this as the next active task. Before using Excel workflow as final
proof, update workflow commands to the new E07 backend semantics:

- own-funds scenarios must pay through `CashAccount`, not procurement balance;
- partnership scenarios continue using capital pool;
- partnership + supplier credit must be rejected;
- partial receives must pass explicit batch capital allocations when needed;
- receive batches and lots must remain immutable after creation;
- generated data must expose enough records for future unified workspace smoke
  tests.

## Current Dry-Run Status

`excel_workflow_audit --dry-run` currently succeeds.

It covers the canonical partnership procurement path:

- investment/operator capital;
- procurement capital pool;
- item and customs payment from capital pool;
- partial receive with explicit batch capital allocation;
- stock transfer;
- POS sales replay.

Known limitations before Phase 3 can be called complete:

- it does not prove own-funds procurement paid from `CashAccount`;
- it does not prove own-funds deferred/installment/consignment settlement;
- it still contains audit warnings about Excel warehouse gaps that are handled
  by explicit audit transfers;
- it should remain the canonical Excel case, but E07 needs additional smoke seed
  scenarios around the Excel workflow.

## Clean Schema Reset Result

Completed on 2026-05-13:

- old local app migration files were removed;
- new initial app migrations were generated from current models;
- local dev DB `microposs` was dropped/recreated;
- schema was applied from the clean migration graph;
- E07 targeted tests passed on the new migration history;
- staged Excel workflow rebuilt local data through:
  `baseline → procurements → transfers → sales → final`.

Current limitation:

- Excel workflow still proves the canonical partnership case only;
- E07 still needs additional smoke seed scenarios for own-funds and supplier
  settlement combinations.

## Acceptance Criteria Before Treating Excel As Final Proof

Phase 3 is complete when:

- reset strategy is documented;
- user explicitly confirms local DB cleanup;
- local DB is rebuilt through staged workflow;
- Excel workflow is updated where old own-funds balance assumptions remain;
- smoke checks prove the rebuilt data covers E07 target scenarios.
