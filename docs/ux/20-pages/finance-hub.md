# SCN-OWN-006 / Finance Hub

## Route
- Target route after PR-11: `/finance`

## Roles
- owner

## Goal
Собрать в одном хабе finance/cash/FX/journal-level operational screens без превращения mobile UI в перегруженный backoffice.

## Primary actions
- открыть cash accounts
- просмотреть FX rates / exchange actions
- открыть journals / finance operations
- перейти к expenses / refunds / owner contributions

## Key UI sections
- finance navigation cards
- account summary cards
- FX status section
- recent journal/operation feed

## Mandatory states
- loading
- empty sections
- error
- forbidden

## Critical UX requirements
- finance hub should act as mobile-first launcher, not as one mega-screen with all dense data
- cards/sections first, detailed tables only at larger breakpoints or deeper screens

## Dependencies
- cash accounts
- exchange rates
- finance operations
- journal feed
