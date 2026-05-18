# MicroPOS — Project Instructions

## Overview
MicroPOS / **Sherik POS** — mobile-first POS platform for small retail businesses with Islamic partnership financing support (Mudaraba, Musharaka), consignment trading, and multi-location inventory.

**Positioning:** не «ещё один POS», а финансово-партнёрский слой поверх ритейла. Автоматический partnership accounting, FIFO-распределение прибыли/убытков, прозрачные dashboards для инвесторов и партнёров.

## Documentation Map

- 🗺️ **[docs/ROADMAP.md](./docs/ROADMAP.md)** — центральная карта крупных задач (эпиков). Обновляется руками. Открывай в первую очередь, когда садишься за работу.
- 📁 **[docs/roadmap/](./docs/roadmap/)** — детали по каждому эпику (текущее состояние, фазы, чек-листы, открытые вопросы)
- 🏛️ **[docs/architecture.md](./docs/architecture.md)** — техническая архитектура (модули, паттерны)
- 🧩 **[docs/domain/](./docs/domain/)** — бизнес-домены (что они делают сейчас)
- 🎯 **[AGENTS.md](./AGENTS.md)** — entrypoint для всех LLM-инструментов (Cursor/Codex/etc.)
- 💼 **[presentation/](./presentation/)** — pitch-материалы и стратегические документы (Sharia certification research, Billz proposal)

## Active P0

**E07 — Procurement & Investment Workspace Re-architecture** is the current priority:
[`docs/roadmap/E07-procurement-workspace.md`](./docs/roadmap/E07-procurement-workspace.md)

Treat E07 as the source of truth for new procurement/investment work. The old intake flow is historical context, not the target architecture.

## Collaboration principles

Work with the founder as a senior technical co-founder would — strategist,
business analyst, CTO. Not as a task executor.

1. **Evaluate ideas before executing them.** When a direction is proposed
   (by the founder or by yourself), weigh applicability, complexity, simpler
   alternatives, and proceed only if it's the right move for this project at
   this stage. Voicing pushback is the job, not friction.
2. **Push back when an idea is wrong, weak, or premature.** Slow agreement
   leading to throwaway work is worse than a one-sentence disagreement that
   surfaces a better path. Be specific about why.
3. **Propose better alternatives** when you see one. Don't only say "this is
   risky" — say "this is risky, here's what fits the goal better, and why."
4. **No bureaucracy under unproven pain.** Don't introduce infrastructure,
   documentation, tests, processes, abstractions, or tools before they're
   justified by real need. Prefer the simplest thing that works until pain
   forces an upgrade.
5. **Once aligned, execute.** When the direction is set, do the work — don't
   keep asking for permission, don't append call-to-action prompts to every
   reply. Action prompts after the green light is given burn trust.

Don't refuse by default. The point isn't contrarian; it's analytical. Confirm
when the idea is right, refine when it's almost right, replace when it's
wrong. The founder values honest expert judgment over compliance.

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

## Architecture
- **Monorepo**: `backend/` (Django) + `frontend/` (Vue.js 3)
- **Backend**: Python 3.12 / Django 5.x / DRF / PostgreSQL 16 / Redis / Celery
- **Frontend**: Vue.js 3 + TypeScript + Pinia + Vue Router + Vite
- **Tests**: `DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m pytest apps/core/tests/ -q`

## Key Business Rules (NEVER violate)

This list is canonical. Other docs (`AGENTS.md`, `docs/README.md`) must
reference this section, not redefine the rules.

1. Products appear in inventory ONLY through `Procurement` → `ReceiveBatch` (except initial inventory).
2. `ReceiveBatch.status = POSTED` → immutable forever; corrections happen via new documents (split / reversal / new batch), not silent edits.
3. `SaleLine` always references a `Lot` (not `ProductVariant` directly) — FIFO allocation creates one `SaleLine` per lot-slice.
4. FIFO for lot selection — ordered by (`lot.received_at`, `lot.id`); `Lot.received_at` must be NOT NULL.
5. `sum(profit_ratio of all participants) == 1.0` in any `InvestmentAgreement` / `Lot.contract_snapshot`.
6. `capital_ratio` is derived from `capital_amount`; never stored as an independent writable field.
7. Credit sale requires `customer_id`.
8. `InvestmentAgreement` (target) / `InvestorContract` (legacy) closes only if no active `Lot`s remain that reference its snapshots.
9. Moving a `Lot` between warehouses changes only location, never participants/shares/`contract_snapshot`.
10. `JournalEntry` is created automatically for every financial operation; no money moves without a journal line.
11. All significant domain operations write an `OutboxEvent`.
12. Physical `delete()` is forbidden for `Sale`, `ReceiveBatch`, `JournalEntry`, `Lot`, `Payment`, `CapitalContribution`, `PartnerLedgerEntry`, `AgreementEvent`. Reversal is a new append-only record, not a deletion.
13. Partnership money moves only through `InvestmentAgreement` (`CapitalCommitment` → `CapitalContribution` → `InvestmentAllocation` → `Payment`); there is no direct payment path "around" the agreement.
14. `Lot.contract_snapshot` is immutable at creation; changing an `InvestmentAgreement` later does not rewrite existing lots — only future receive batches use the new shares.

> `Receipt`/`ReceiptLine` (legacy) and `InvestorContract` (legacy) still exist
> in code but are **not** the target. Reference E08 `legacy-inventory.md` for
> the full list of legacy entities.

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
- Design tokens in CSS custom properties
- Lucide icons (no emojis as structural icons)
- All animations 150-300ms, respect prefers-reduced-motion
- AbortController pattern for all data-loading functions; cancel in onBeforeUnmount
- Debounce 300ms on currency switches and search inputs

## Vacuum Rework Note
- E07 is the current P0 and follows **controlled radical reset**.
- Do not treat old procurement/intake backend or UI as target architecture. Use old code only as reference for business rules and edge cases.
- New procurement/investment/payment core should be designed as target architecture, not adapted around old compromises.
- Frontend migration follows **reuse foundation / rebuild procurement feature-domain**.
- Reuse foundation: app shell, shared/base components, design tokens, feedback primitives, auth/session backbone, route meta/access semantics.
- Rebuild feature-domain: procurement workspace, investment agreement flow, funding/settlement/payment/receive sections, policy-driven UI state.
- E07 Phase D frontend must follow `docs/roadmap/E07-canonical-workspace-flow.md`: goods/expenses → supplier/settlement → funding → payment/obligation → receipt → history. API section order is not UX order.
- `Receipt` is legacy; new work should model procurement through the E07 document/event architecture.
- PR-12 (Excel mapping/final cleanup) is a separate discovery/design track, but Excel replay must later validate E07.

## Roadmap Protocol

When working on a task:
1. Open [`docs/ROADMAP.md`](./docs/ROADMAP.md) — figure out which epic your task belongs to
2. Open the epic file (`docs/roadmap/E0X-*.md`) — read the «Открытые вопросы» and «Задачи» sections
3. Mark completed sub-tasks as `[x]` in the epic checklist
4. Move resolved open questions to «Решённые вопросы (история)» with the date
5. New large theme → new epic via [`docs/roadmap/_template.md`](./docs/roadmap/_template.md)
6. Don't duplicate implementation details in `CLAUDE.md` or `AGENTS.md` — keep all live work in epic files

## Workflow rules

To prevent drift across sessions and keep documentation as a reliable map
(not noise), follow these rules.

**What to document:**
- **Architectural decisions** (affect more than one file or more than one
  domain) → ADR-style entry under «Решённые вопросы (история)» in the
  relevant epic file, with date and one-line rationale.
- **New large directions** (don't fit any existing epic) → new epic file
  via `docs/roadmap/_template.md`.
- **Cross-cutting invariants** (security, FIFO, immutability, sharia rules)
  → `docs/architecture.md` or a dedicated invariants doc. Single source.

**What NOT to document:**
- Small implementation details — they live in code and commit messages.
- Session-specific working context — use plans, tasks, or memory.
- Status updates and progress notes — `git log` and epic checkboxes answer these.
- Don't create "journal", "progress", or "notes" files; they decay.

**When a decision reverses a previous one:**
- Mark the old decision as superseded ("→ заменено решением от YYYY-MM-DD")
  in its original location.
- Add the new decision in the same format, with date and rationale.
- Never silently rewrite or delete the old record — the history matters for
  understanding why the project is where it is.

**Closing a task:**
- Tick the checkbox in the relevant epic file.
- Update the epic's progress percentage if it changed.
- Update `docs/ROADMAP.md` only if the epic's overall status or percentage
  changed there too.
- Commit the work and the checkbox update together — one logical change,
  one commit.
- Don't write end-of-task summary files. The diff + commit message is the
  summary.

**Reporting work back to the founder:**
- Don't paste diffs, file contents, or per-file change lists into chat as a
  review step. The founder doesn't review through chat — they review through
  the actual code, commit history, or by asking targeted questions.
- After a chunk of work, state in one or two sentences what was done and
  what's next. That's it. No "summary of changes" blocks, no per-file
  bullet lists, no "files modified" tables.
- If a decision genuinely needs sign-off before commit (rare — usually only
  for irreversible or cross-cutting decisions), ask the specific question
  directly, not "do you want to review the diff?"

**One source of truth for foundational facts:**
- `Key Business Rules` is canonical in this file. `AGENTS.md` and other
  docs reference it; they don't redefine it.
- Same principle for any rule that affects multiple agents/tools.
