# SCN-OWN-003 / Procurement Create

## Route
- Target route after PR-11: `/procurements/create`

## Roles
- owner
- warehouse (restricted operational variant may be allowed later if needed)

## Goal
Создать новую закупку под vacuum-model: оформить procurement, контракт/партнёров, товары, расходы и подготовить сценарий receive.

## Primary actions
- выбрать тип закупки
- задать партнёров и доли
- задать товарные позиции
- задать расходы
- сохранить draft/open procurement
- перейти к receive when balance == 0 flow

## Key UI sections
- procurement type selector
- partner/contract block
- procurement items block
- expenses block
- balance summary
- sticky CTA area

## Mandatory states
- loading
- empty defaults
- validation error
- submit success
- forbidden

## Critical invariants in UI
- partnership flow requires OPERATOR in contract
- `mudaraba_ratio` in `[0..1]`
- receive not available until balance is zero
- mobile flow must avoid giant single-form overload

## Dependencies
- `/api/v1/partnerships/procurements/`
- `/api/v1/catalog/variants/`
- `/api/v1/suppliers/suppliers/`
- `/api/v1/inventory/warehouses/`

## API contract note
- Procurement create submit must include `client_request_id` for idempotent create-procurement behavior.
- Duplicate submit with same `client_request_id` must resolve predictably (no duplicate procurement).

## Acceptance criteria
- partnership contract block validates operator/investor composition before submit
- invalid contract/items/expenses combinations surface explicit field/section errors
- successful create lands on created procurement detail with visible status and next action
- receive action is not offered directly from create screen unless procurement state is truly ready
