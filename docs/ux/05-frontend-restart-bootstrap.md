# Frontend Restart Bootstrap (P0)

## Purpose
Зафиксировать стартовую архитектуру и последовательность запуска после intentional wipe `frontend/`.

## Current baseline (2026-04-19)
- `frontend/` больше не пустой: создан новый scaffold P0 foundation.
- Старые legacy frontend-файлы не считаются рабочей основой.
- Источник требований для рестарта: `docs/ux/*` + backend contracts.

## P0 target outcome
Минимум, который должен появиться до широкого feature-кодинга:
1. Buildable app shell.
2. Auth bootstrap + role-aware route guards.
3. Canonical P0 routes (без legacy naming drift).
4. Первая рабочая вертикаль: login -> role-home -> core role screen.

## Architecture entrypoint (must create first)
1. `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`.
2. `frontend/src/main.ts`, `frontend/src/App.vue`.
3. `frontend/src/router/index.ts`, `frontend/src/router/routes.ts`.
4. `frontend/src/api/client.ts`.
5. `frontend/src/stores/auth.ts`, `frontend/src/stores/session.ts`, `frontend/src/stores/ui.ts`.
6. `frontend/src/assets/styles/tokens.css` (+ reset/typography/animations as needed).
7. `frontend/src/components/base/*` и `frontend/src/components/feedback/*` (минимальный набор для P0).

## Startup sequence (strict)
1. **Tooling bootstrap**: Vite + Vue + TS + Pinia + Router.
2. **Shell bootstrap**: `<router-view/>`, global styles, base error/toast primitives.
3. **Auth bootstrap**: login (`/api/v1/auth/token/`) + me/profile load.
4. **Tenant bootstrap**: использовать серверный tenant context; не хардкодить tenant в UI.
5. **Route guards**: `meta.roles` + unauth/auth redirects.
6. **Role-home resolver**:
   - owner -> `/sales`
   - cashier -> `/sales`
   - warehouse -> `/procurements`
   - investor -> `/investor`
7. **P0 feature slices** (по порядку):
   - login
   - sales-catalog -> cart -> checkout
   - procurements-list -> procurement-detail (receive readiness)
   - investor-dashboard -> investor procurements
   - settings
8. **Temporary startup policies**:
   - cashier may read customers/receivables, but owner performs create/pay mutations
   - owner dashboard remains launchpad; reports stay separate and later-scope
   - investor payout-history / aggregate ledger is P1 alignment, not P0 blocker
   - receiving remains inside procurements flows, without separate `/receiving` route in P0
9. **P0 hardening**: loading/empty/error/forbidden states + idempotent submit on critical POST flows.

## Module boundaries (normative)
- `src/components/base|feedback` — без domain-логики.
- `src/router/*` — только routing/access orchestration.
- `src/api/*` — typed transport/endpoint wrappers; без UI-state.
- `src/stores/*` — domain/application state orchestration.
- `src/modules/<domain>/*` — только feature screens/components конкретного домена.
- Запрещено: прямой импорт view->view из другого домена.
- Запрещено: смешивание investor shell с owner/cashier shell.
- Role-gating rule: route-level guard + UI action-level guard обязательны одновременно; нельзя полагаться только на hidden buttons.

## Canonical P0 route set
| Route | Roles | Screen ID |
|---|---|---|
| `/login` | public | SCN-AUTH-001 |
| `/sales` | owner, cashier | SCN-CSH-001 |
| `/sales/cart` | owner, cashier | SCN-CSH-003 |
| `/sales/checkout` | owner, cashier | SCN-CSH-004 |
| `/procurements` | owner, warehouse | SCN-OWN-002 / SCN-WHS-001 |
| `/procurements/:id` | owner, warehouse | SCN-OWN-004 / SCN-WHS-002 |
| `/investor` | investor | SCN-INV-001 |
| `/investor/procurements` | investor | SCN-INV-002 |
| `/investor/procurements/:id` | investor | SCN-INV-003 |
| `/settings` | all authenticated roles | SCN-COM-001 |

## Alias policy for restart
- Canonical language: **procurements**, не intake.
- Canonical investor detail: `/investor/procurements/:id`.
- Legacy aliases (`/intake/*`, `/investor/contracts/:id`) не входят в P0 scope.

## Definition of Ready for any P0 screen
Экран можно брать в разработку только если в его spec есть:
- route + roles,
- goal + primary actions,
- states: loading/empty/error/forbidden (+ success where submit exists),
- backend dependencies,
- acceptance criteria.

## Cross-links
- Route policy/details: `docs/ux/15-route-screen-matrix.md`
- Open blockers: `docs/ux/16-open-decisions-and-conflicts.md`
- Foundation restore map: `docs/ux/18-foundation-keep-delete-plan.md`
- Cleanup status: `docs/ux/19-frontend-cleanup-execution.md`
