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
- partnerships contracts
- products/variants data
- suppliers
- warehouses for receive step
