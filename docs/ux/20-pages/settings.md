# SCN-COM-001 / Settings

## Route
- `/settings`

## Roles
- owner
- cashier
- warehouse
- investor

## Goal
Дать единое место для языка, темы, сессии и базовых персональных настроек без role-specific business noise.

## Primary actions
- сменить язык
- сменить тему/visual mode if supported
- управлять сессией/logout
- увидеть базовую информацию о текущей роли

## Key UI sections
- language settings
- theme / appearance
- session controls
- role/account info

## Mandatory states
- loading
- error
- success feedback

## UX note
Этот экран остаётся shared utility screen для всех ролей и не должен смешиваться с business admin settings.
