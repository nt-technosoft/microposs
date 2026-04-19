# SCN-AUTH-001 / Login

## Route
- `/login`

## Roles
- public entry

## Goal
Дать быструю, понятную и role-aware точку входа в продукт без лишнего когнитивного шума.

## Primary actions
- ввести логин/пароль
- войти
- при успехе перейти в role-home

## Entry points
- direct open
- redirect from protected route
- post-logout entry

## Exit points
- owner/cashier -> sales home
- warehouse -> procurement/receiving home
- investor -> investor dashboard

## Required states
- loading submit
- invalid credentials
- expired session return
- success redirect

## Functional requirements
- auth request to `/api/v1/auth/token/`
- restore redirect target if relevant
- on success trigger `auth/me` load

## Non-functional requirements
- mobile first
- immediate focus on credentials
- clear error copy near action area

## Acceptance criteria
- wrong credentials show clear error
- valid login lands on role-home
- no extra onboarding noise on first screen
