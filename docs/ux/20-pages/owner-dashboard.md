# SCN-OWN-001 / Owner Dashboard

## Route
- Target route after PR-11: `/dashboard` or `/home`

## Roles
- owner

## Goal
Дать owner быстрый operational overview без превращения главного экрана в аналитическую перегрузку.

## Primary actions
- увидеть health snapshot бизнеса
- перейти в procurements / finance / sales / stock problem areas
- увидеть alerts and pending actions

## Key UI sections
- priority action cards
- business health summary
- pending tasks / alerts
- quick links to core modules

## Mandatory states
- loading
- empty baseline state
- error
- forbidden

## Critical UX requirements
- главное: priority and actionability, не dense reporting
- must work as mobile launchpad for owner
- financial/admin depth уходит в deeper screens, не на first fold

## Dependencies
- high-level sales/procurement/finance/stock summaries
- alerts / blocked states
