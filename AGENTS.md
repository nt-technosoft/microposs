# MicroPOS — Agent Instructions

## Overview
MicroPOS / **Sherik POS** — mobile-first платформа: финансово-партнёрский слой для retail-бизнеса с поддержкой исламского партнёрского финансирования (Мударабá, Мушарáка), консигнации, мульти-локаций и мульти-валют.

Это **не «ещё один POS»**. Это слой, который автоматически ведёт партнёрский учёт: фиксация долей в момент прихода товара, FIFO-распределение прибыли и убытков, прозрачные dashboard'ы для инвесторов и партнёров.

**Full documentation:** `docs/README.md` → links to all domain docs.

## Collaboration principles

This project is led by a single founder who works through AI agents as a
strategic partner, not as a task executor. Any agent (Claude Code, Codex,
Cursor, etc.) is expected to:

1. **Evaluate ideas before executing.** Weigh applicability, complexity, and
   alternatives. Push back when an idea is wrong, weak, or premature. Voicing
   pushback is the job, not friction.
2. **Propose better alternatives** when you see one — don't only point out risks.
3. **No bureaucracy under unproven pain.** Don't add infrastructure, docs,
   tests, or abstractions before they're justified by real need.
4. **Once aligned, execute.** Don't append call-to-action prompts after a
   green light has been given.

For the long form (with rationale and workflow rules: what to document, when
a decision reverses a previous one, how to close a task), see [`CLAUDE.md`](./CLAUDE.md)
— sections **"Collaboration principles"** and **"Workflow rules"**. These
apply to all agents on this project, not only Claude.

## 🗺️ Active Roadmap

**Центральная карта крупных задач:** [`docs/ROADMAP.md`](./docs/ROADMAP.md) — обзорная таблица всех эпиков, статусы и прогресс.

**Текущие эпики:**
- E01 — Suppliers & Procurement (расширенная модель) → [doc](./docs/roadmap/E01-suppliers-procurement.md)
- E02 — Product–Supplier Links → [doc](./docs/roadmap/E02-product-supplier-links.md)
- E03 — Real Value Reporting (Net Asset View) → [doc](./docs/roadmap/E03-real-value-reporting.md)
- E04 — Contract Types Formalization → [doc](./docs/roadmap/E04-contract-types.md)
- E05 — Zakat Calculation → [doc](./docs/roadmap/E05-zakat.md)
- E06 — Sharia Certification → [doc](./docs/roadmap/E06-sharia-certification.md)
- E07 — Procurement & Investment Workspace Re-architecture → [doc](./docs/roadmap/E07-procurement-workspace.md) **P0 / главный активный цикл**

**Roadmap-протокол** (для любого LLM-инструмента, работающего с задачами):
1. Открой [`docs/ROADMAP.md`](./docs/ROADMAP.md) → определи свой эпик
2. Открой файл эпика → читай «Открытые вопросы» и «Задачи»
3. Сделанные подзадачи отмечай `[x]` в чек-листе
4. Решённые открытые вопросы — переноси в «Решённые вопросы (история)» с датой
5. Новая крупная тема → новый эпик по [`docs/roadmap/_template.md`](./docs/roadmap/_template.md)

## Quick Reference

## Architecture-First Delivery Policy

For large epics, domain rewrites and foundational features, optimize for the
target architecture, not for a locally green or cosmetically complete state.

- Do not write tests for the sake of tests. Tests must validate the intended
  business behavior and target architecture.
- Do not add shims, aliases, hidden compatibility layers or temporary
  workarounds only to make old tests, old UI or old services pass.
- A temporarily incomplete or red intermediate state is acceptable during a
  planned reset if the roadmap clearly explains how the final architecture will
  become consistent.
- When conflicts appear, resolve them at the architecture/domain boundary:
  decide which model, service, module or contract should change long-term
  instead of patching the local symptom.
- Before implementing large changes, check how the decision affects adjacent
  domains: inventory/FIFO, finance/journals, suppliers/payables,
  partnerships/profit, reporting, frontend state and Excel replay.
- Prefer explicit target contracts over silent backward compatibility. Old code
  can remain as reference, but must not dictate the new model.
- Verification is still required, but it should prove the target behavior. Do
  not treat legacy-suite green as success if it required compromising the
  architecture.
- For confirmed large epics such as E07, continue in larger coherent slices
  until a real blocker appears. Do not stop after every micro-task just to
  report progress or ask for permission when the roadmap and target contracts
  provide enough context.
- Use planning when it improves execution quality, then execute the plan.
  Periodically re-check the architecture, domain boundaries and adjacent-module
  effects, but avoid wasting cycles on premature full-suite verification while
  the reset is intentionally incomplete.

### Where to find business logic
| Domain | Backend service | Frontend module |
|---|---|---|
| Inventory / Lots / FIFO | `apps/inventory/services.py` | `src/modules/inventory/` |
| Procurement / Receipt | `apps/partnerships/services.py` | `src/modules/intake/` |
| Sales / POS / Returns | `apps/sales/services.py` | `src/modules/sales/` |
| Finance / Accounting | `apps/finance/services.py` | `src/modules/finance/` |
| Partnerships / Profit | `apps/partnerships/services.py` | `src/modules/investors/` |
| Customers / Debt | `apps/customers/services.py` | — |
| Suppliers / Payables | `apps/suppliers/services.py` | — |
| Reporting | `apps/finance/views.py` | `src/modules/reports/` |
| Async aggregation | `apps/analytics/tasks.py` | — |

### Key files
- `backend/apps/finance/views.py` — combined report endpoints, profitability views, caching
- `backend/apps/analytics/tasks.py` — OutboxEvent processing, DailySummary aggregation
- `frontend/src/modules/reports/views/ReportsDashboard.vue` — main reporting screen
- `frontend/src/api/finance.ts` — typed finance API client
- `frontend/src/router/index.ts` — auth guard + role routing

### Running tests
```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m pytest apps/core/tests/ -q
```
Run this before treating backend/domain changes as complete.

### Canonical Excel workflow
Use `docs/testing-data-workflow.md` as the source of truth.

- Canonical source file: `MUZORABA USTOZ VA BEKZOD AKA 2 (1).xlsx`
- Canonical snapshot: `backend/import_snapshots/muzoraba_ustoz_bekzod_latest.json`
- Current commands:
  - `excel_snapshot_from_xlsx` — rebuild snapshot from `.xlsx`
  - `excel_workflow_staged` — staged manual-audit replay
  - `excel_workflow_audit` — full one-shot replay after staged flow is trusted

Do not use retired direct-import scripts. Test data must be generated through
domain services/API-like flows, not by inserting final Excel totals into reports.

### Thread / context handoff
For large tasks, prefer a fresh Codex thread per epic/task. Keep durable context
in this file, `docs/ROADMAP.md`, domain docs, and tests. Before starting a new
thread, summarize: branch, goal, changed files, relevant docs, commands to run,
and unresolved risks.

## Architecture
- **Monorepo**: `backend/` (Django) + `frontend/` (Vue.js 3)
- **Backend**: Python 3.12 / Django 5.x / DRF / PostgreSQL 16 / Redis / Celery
- **Frontend**: Vue.js 3 + TypeScript + Pinia + Vue Router + Vite

## Key Business Rules

**Canonical source:** [`CLAUDE.md` → Key Business Rules](./CLAUDE.md#key-business-rules-never-violate). Do not redefine the rules here — read them there. This section is intentionally a pointer, not a copy.

## Backend Conventions
- All models inherit `core.BaseModel` (soft-delete, timestamps)
- Domain apps don't import each other's models for business logic
- Cross-domain communication: services layer + OutboxEvent
- ForeignKey across domains is allowed
- Service layer pattern: `services.py` in each app
- All POST endpoints for financial ops accept `client_request_id` (idempotency)
- Multi-tenant: `tenant_id` on all business data models
- Immutable financial records after confirmed/completed status
- `CELERY_TASK_ALWAYS_EAGER=True` in development settings — tasks run synchronously in dev/test

## Frontend Conventions
- Mobile-first, responsive (375px → 768px → 1024px → 1440px)
- Vue 3 Composition API + `<script setup>` syntax
- Pinia stores per domain
- API layer in `src/api/` with typed clients
- Components: `src/components/` (shared) + `src/modules/<domain>/components/`
- Reuse shared controls before creating new UI controls: `MoneyCurrencyInput` for amount+currency, `BaseSelect` for mobile-friendly selects.
- Design system foundation: MicroPOS CSS tokens + Tailwind CSS v4 + shadcn-vue
  + Reka UI. See `docs/frontend-design-system.md`.
- For any frontend design/redesign, apply the project frontend workflow in
  `.agents/skills/microposs-frontend-design/SKILL.md`: mobile-first, not
  mobile-only; workflow before components; shadcn-vue primitives through domain
  wrappers.
- Lucide icons (no emojis as structural icons)
- Any frontend/UI change must explicitly use `frontend-skill` as part of the workflow
- All animations 150-300ms, respect prefers-reduced-motion
- AbortController pattern for all data-loading functions; cancel in onBeforeUnmount
- Debounce 300ms on currency switches and search inputs

## Important: Celery in dev/test
`CELERY_TASK_ALWAYS_EAGER=True` is set in `config/settings/development.py`. This means all `.delay()` calls execute synchronously — no Celery worker needed in development. Tests rely on this behaviour.

## Vacuum Rework Note
- E07 is the current P0 and follows **controlled radical reset**.
- Do not treat old procurement/intake backend or UI as target architecture. Use old code only as reference for business rules and edge cases.
- New procurement/investment/payment core should be designed as target architecture, not adapted around old compromises.
- Frontend migration: reuse foundation, but rebuild the procurement feature-domain around one workspace.
- E07 Phase D frontend must follow `docs/roadmap/E07-canonical-workspace-flow.md`: goods/expenses → supplier/settlement → funding → payment/obligation → receipt → history. API section order is not UX order.
- `Receipt` is legacy; new work should model procurement through the E07 document/event architecture.
- PR-12 (Excel mapping) is a separate track, not a default continuation, but Excel replay must later validate E07.
