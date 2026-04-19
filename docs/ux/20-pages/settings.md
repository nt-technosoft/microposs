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
- forbidden (for corrupted/invalid auth state)

## Dependencies
- auth/session profile (`/api/v1/auth/me/`)

## Acceptance criteria
- role/account info is sourced from authenticated profile and updates after relogin
- logout always returns user to `/login` and clears role-scoped navigation state
- settings screen never includes owner-only business admin actions

## UX note
Этот экран остаётся shared utility screen для всех ролей и не должен смешиваться с business admin settings.

## Open decision
- Which settings persist server-side vs local-only remains to be finalized during implementation.
