# SCN-WHS-001 / Receiving Queue

## Route
- Target route after PR-11: `/procurements` with warehouse-focused filter or `/receiving`

## Roles
- owner
- warehouse

## Goal
Показать закупки, которые требуют operational действий склада: review, readiness check, receive.

## Primary actions
- открыть закупку
- увидеть receive readiness
- отфильтровать open / ready / blocked items
- перейти в receive detail

## Key UI sections
- status filters
- procurement cards/list
- readiness indicators
- receive CTA / blocked reason

## Mandatory states
- loading
- empty queue
- error
- forbidden

## Critical invariants in UI
- закупка с non-zero balance не должна выглядеть как ready-to-receive
- blocked reason должен быть виден прямо в списке или в один тап
- mobile list must prioritize actionable status over dense metadata

## Dependencies
- procurement list
- procurement balance summary
- receive readiness state
