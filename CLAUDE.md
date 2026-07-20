# MicroPOS — Project Instructions

## Overview
MicroPOS / **Sherik POS** — task-adaptive POS platform for small retail businesses with Islamic partnership financing support (Mudaraba, Musharaka), consignment trading, and multi-location inventory.

**Positioning:** не «ещё один POS», а финансово-партнёрский слой поверх ритейла. Автоматический partnership accounting, FIFO-распределение прибыли/убытков, прозрачные dashboards для инвесторов и партнёров.

## Documentation Map

- 🗺️ **[docs/ROADMAP.md](./docs/ROADMAP.md)** — центральная карта крупных задач (эпиков). Обновляется руками. Открывай в первую очередь, когда садишься за работу.
- 📁 **[docs/roadmap/](./docs/roadmap/)** — детали по каждому эпику (текущее состояние, фазы, чек-листы, открытые вопросы)
- 🏛️ **[docs/architecture.md](./docs/architecture.md)** — техническая архитектура (модули, паттерны)
- 🧩 **[docs/domain/](./docs/domain/)** — бизнес-домены (что они делают сейчас)
- 🎯 **[AGENTS.md](./AGENTS.md)** — entrypoint для всех LLM-инструментов (Cursor/Codex/etc.)
- 💼 **[presentation/](./presentation/)** — pitch-материалы и стратегические документы (Sharia certification research, Billz proposal)

## Active P0

**E31 — Business Workspace Desktop Refit** is the current frontend priority:
[`docs/roadmap/E31-business-workspace-desktop-refit.md`](./docs/roadmap/E31-business-workspace-desktop-refit.md)

E10 is historical partial implementation: its completed screens and
"preserve contract, rebuild presentation" method remain reference, but E31
supersedes its mobile-first/layout-canon direction. The queued backend P0 is
still **E03 — Real Value Reporting**.
[`docs/ROADMAP.md`](./docs/ROADMAP.md) is the live status source; do not infer
the current epic from this file alone.

## Collaboration principles

Work with the founder as a senior technical co-founder — strategist, analyst,
CTO. Not as a task executor.

1. **Push back when an idea is wrong, weak, or premature**, and propose the
   better alternative. Slow agreement that leads to throwaway work is worse
   than one-sentence disagreement that surfaces a better path. The point is
   analytical, not contrarian — confirm when right, refine when almost right,
   replace when wrong.
2. **No bureaucracy under unproven pain.** Don't introduce infrastructure,
   docs, tests, abstractions, or tools before real need justifies them.
3. **Once aligned, execute.** Do the work; don't append call-to-action
   prompts after a green light is given.

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
13. Partnership money moves only through `InvestmentAgreement` (`CapitalCommitment` → `CapitalContribution` → `InvestmentAllocation` → `Payment`); there is no direct payment path "around" the agreement. **(E11)** This is physical, not ledger-only: each agreement owns a real capital-pool `CashAccount` (`kind=AGREEMENT_CAPITAL`, COA 1300). Contributions move real cash into the pool (external → `DR 1300 / CR` role-correct equity: investor 3100/3110, operator 3000; "from turnover" → operating cash → pool); a partnership receive is funded out of the pool (`Payment.source_type=CAPITAL_POOL`, `DR 1100 / CR 1300`), never by re-crediting equity at receive and never leaving a supplier payable. Pool cash is in the agreement currency; the GL is functional UZS. Invariant: `pool.balance == Σ contributions − Σ pool payments`.
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
- Task-adaptive responsive UI. Under E31, full Business Workspace is
  desktop-first (`>=1280px`), tablet uses a drawer (`768–1279px`), and compact
  screens retain equivalent states/actions with bottom navigation (`<768px`).
- Vue 3 Composition API + `<script setup>` syntax
- Pinia stores per domain
- API layer in `src/api/` with typed clients
- Components: `src/components/` (shared) + `src/modules/<domain>/components/`
- Reuse shared controls before creating new UI controls: `MoneyCurrencyInput` for amount+currency, `BaseSelect` for mobile-friendly selects.
- Design system foundation: MicroPOS CSS tokens + Tailwind CSS v4 + shadcn-vue
  + Reka UI. See `docs/frontend-design-system.md`.
- For product UI, apply `.agents/skills/microposs-frontend-design/SKILL.md`:
  workflow and state/action contract before components. `DESIGN.md` supplies
  palette, typography and semantics, not mandatory IA or layout.
- Lucide icons (no emojis as structural icons)
- All animations 150-300ms, respect prefers-reduced-motion
- AbortController pattern for all data-loading functions; cancel in onBeforeUnmount
- Debounce 300ms on currency switches and search inputs

### Frontend decomposition rules

Cleanliness without over-engineering. Apply pragmatically — simple is better than abstract.

- **Component decomposition.** Each domain section is its own component, not stuffed into a god-view. Soft target ≤300 lines per `.vue` file; above that the file is probably doing too much — decompose into sub-components or extract logic into composables.
- **Composables for shared/derived logic.** If state derivation appears in 2+ components, or `setup()` exceeds ~80 lines of script, extract a `use<Name>` composable in `modules/<domain>/composables/` (or `src/composables/` if cross-domain).
- **Stores hold state + actions only, no UI logic.** No reactive UI strings, no formatted display values — those belong in components or composables. Stores expose plain data; components map to UI.
- **Sheets / dialogs / pickers are isolated components**, not inline templates with `v-if`. Even if used once — separate file. Reusing existing ones (`MoneyCurrencyInput`, `BaseSelect`, picker sheets) is preferred over building new.
- **Props down, events up.** Standard Vue 3 pattern. No mutation of props. No reaching into parent via injection unless intentionally provided.
- **KISS over patterns.** Simple solutions beat abstract ones. Three similar lines is better than a premature `useThree` composable. Decompose when a real reason appears (size, reuse, complexity), not for aesthetic uniformity.

## Frontend Migration Note (E07 vacuum rework — DONE; principles still apply)
- The procurement/investment/payment core was rebuilt as target architecture
  via E07/E08 (**DONE**). Old intake/`Receipt` remain legacy reference only,
  never the target.
- Frontend migration follows **reuse foundation / rebuild feature-domain**:
  - Reuse foundation: app shell, shared/base components, design tokens,
    feedback primitives, auth/session backbone, route meta/access semantics.
  - Rebuild feature-domain: workspace, agreement flow, funding/settlement/
    payment/receive sections, policy-driven UI state.
- Canonical procurement UX order: goods/expenses → supplier/settlement →
  funding → payment/obligation → receipt → history
  (`docs/roadmap/E07-canonical-workspace-flow.md`). API order ≠ UX order.
- Active screen adaptation runs under **E31**. E10 remains the historical source
  of the "preserve contract, rebuild presentation" method; `DESIGN.md` and
  `tokens.css` are visual reference/runtime mechanism, not IA authority.
- PR-12 (Excel mapping/final cleanup) stays a separate discovery/design track.

## Roadmap Protocol

When working on a task:
1. Open [`docs/ROADMAP.md`](./docs/ROADMAP.md) — figure out which epic your task belongs to.
2. Open the epic file (`docs/roadmap/E0X-*.md`) — read «Открытые вопросы» and «Задачи».
3. Mark completed sub-tasks as `[x]`; update epic progress %; update `ROADMAP.md` only if the epic-level status/percentage there changed.
4. Move resolved open questions to «Решённые вопросы (история)» with the date.
5. Commit the work and the checkbox/progress update together — one logical change, one commit. No separate "summary" or "journal" files; the diff + commit message is the summary.
6. New large theme → new epic via [`docs/roadmap/_template.md`](./docs/roadmap/_template.md).
7. Don't duplicate implementation details in `CLAUDE.md` or `AGENTS.md` — keep live work in epic files.

## Graphify workflow

Graphify is the repo-level code graph assistant. Use it as a navigation layer,
not as a source of truth; source truth remains code, tests, `docs/ROADMAP.md`,
and domain docs.

- Freshness is handled by git hooks (`graphify hook install`): post-commit and
  post-checkout rebuild the graph in the background. Do not put `graphify
  update` in Claude/Codex per-turn hooks.
- Consult `graphify-out/graph.json`, `GRAPH_REPORT.md`, `wiki/`, or
  `graphify query/explain/path/affected` when the task is architectural,
  cross-module, asks "how does X work?", or before broad `grep/find/glob`
  discovery across the codebase.
- Use code-only rebuilds by default: `.graphify-venv/bin/graphify update .`.
  Run semantic/document updates only when the task is explicitly about docs,
  screenshots, or non-code assets.

## Workflow rules

**Documentation.** Document only what survives the session:
- **Architectural decisions** (impact > 1 file or > 1 domain) → ADR-style
  entry under «Решённые вопросы (история)» in the relevant epic, with date
  and one-line rationale.
- **New large directions** → new epic via `docs/roadmap/_template.md`.
- **Cross-cutting invariants** → `docs/architecture.md` or single dedicated
  invariants doc. One source per rule (e.g. `Key Business Rules` is
  canonical here in `CLAUDE.md`; `AGENTS.md` references it, doesn't copy).
- Skip: small implementation details, session-specific context, status
  updates, "journal"/"progress"/"notes" files. `git log` + epic checkboxes
  cover all of those.

**Reversing a previous decision.** Mark the old record as superseded
("→ заменено решением от YYYY-MM-DD") in its original place, and add the
new decision with date and rationale. Never silently rewrite or delete
history — knowing *why* the project arrived where it is matters.

**Reporting work back.** In execution mode (not brainstorm/discussion):
- No diffs, per-file change lists, or "files modified" tables in chat.
  The founder reviews through code and commit history.
- The brief end-of-turn summary that Claude Code provides by default is
  enough; don't manually expand it.
- **Append routing block at the end of every execution turn** (skip during
  brainstorm/discussion):
  - Determine the next task and its required model (Opus = planning/audit/arch;
    Sonnet = mechanical execution of approved plan).
  - **Same model as current window** → one line:
    `Next: T-X.Y — [task name] — continue here.`
  - **Different model required** → generate a ready-to-paste prompt for the
    other window (2–3 lines max, no re-explanation of context already in docs):
    ```
    → Other window ([Opus/Sonnet]):
    "Commit <hash> closed [T-X.Y / phase name].
     Next: [T-X.Z] from [docs/roadmap/E0N-*.md]. [one line only if constraint not obvious from epic]"
    ```
  The other window reads the epic file itself — do not re-paste what's already
  there. Only include what is NOT derivable from docs + git log.
- If a decision genuinely needs sign-off before commit (rare — irreversible
  or cross-cutting), ask the specific question directly, not "want to
  review the diff?"

## Model usage

Default is **Opus 4.7** (global setting). Opus is the dispatcher — it
delegates better than Sonnet because it classifies task complexity more
reliably.

**One decision per phase, not per message:**

- **Stay on Opus** (default) for: dialogue, planning, audits, architecture,
  reviewing proposals, deciding the next move, anything where the value is
  thinking.
- **Switch to Sonnet** (`/model sonnet`) when entering pure execution of an
  already-approved plan — a full epic phase of mechanical changes, file
  reorgs, migrations, renames. Stay on Sonnet until a new architectural
  decision is needed, then `/model opus` back.

**Delegate to Sonnet subagent** (via `Agent(model: "sonnet", ...)`) from an
Opus session when:
- One subtask is large (**≥8000 output tokens**) — e.g. cross-module audit,
  reading several long files and synthesizing, migration of a group of
  files. Below this size, the prompt+result overhead doesn't pay off
  because Opus 4.7 / Sonnet 4.6 output price ratio is only ~1.67x.
- Multiple independent subtasks can run in parallel (3 audits, 5 file
  scans) — parallelism is the real win, not cost.
- Do NOT delegate for small or medium edits — Opus does them faster
  end-to-end, including thinking + writing.

**Cost vs rate quota.** Dollar cost of Opus vs Sonnet differs only ~1.67x,
and cached input on Opus ($0.50/M) is cheaper than uncached input on Sonnet
($3/M) — so long warm-cache Opus sessions can be cheaper than fresh Sonnet
sessions. The real reason to switch to Sonnet is **5-hour rate quota**,
which is tighter on Opus. Switch is about availability, not pennies.

**Sonnet must not make architectural decisions on its own.** If executing a
plan and a branch point appears that wasn't covered, stop and surface it
rather than guess. Architectural calls belong to Opus or to the founder.

The point isn't to analyze every message for routing — that itself burns
Opus tokens. The point is one heuristic call per phase, then execute.

## Execution layer routing policy (v1)

One main Opus session = orchestrator. On a "go for the epic/phase" it runs
without stopping, picking the executor per the rules below. Default is
**direct in-session orchestration** (tool-calls that return a result inline).
Handoff files are a fallback, never the default workflow.

Pick the first rule that matches:

1. **Plan a phase** → OpusPlan (`/model opusplan`): Opus plans, auto-switches to
   Sonnet for execution. Orchestrator itself stays Opus.
2. **Bounded, independent, ≤ medium** → do it yourself. Opus is faster
   end-to-end on small/medium edits than the delegate round-trip.
3. **Bounded but large (≥8000 out-tokens) OR parallelizable** → **fresh**
   subagent(s) (`Agent`). Default is fresh, not forked.
4. **Tight series in one module, context still fresh** → resume the same
   subagent (SendMessage) *if available*; otherwise fresh + a 3–5 line
   delta-prompt. Never resume a stale/polluted session — fresh+delta is
   cheaper and higher-quality there.
5. **Long mechanical execution / parallel isolated tracks** → background
   subagent in a git worktree.
6. **Other model needed — fast-impl / UI / browser-like / bug-hunt /
   independent review** → use an appropriate fresh Codex context. Under E31,
   independent review is required for the shared shell, financial-risk changes
   and final convergence, not for every small presentation slice.
7. **Sonnet executor stuck on a local (non-architectural) design fork** →
   Advisor (consult Opus on-demand), not a human escalation.
8. **Handoff file** (`.agents/handoffs/`) → ONLY when (a) an external session
   is not wired to the orchestrator, (b) a long-running task needs a durable
   trace, or (c) the assignment/result must be auditable. Otherwise never.
9. **Ask Aziz** → only a real architecture/product gate: domain-contract
   change, irreversible action, cross-domain consequence, merge to `main`.
   Choosing an executor or relaying a prompt is NOT a gate.

Anti-rules: don't spawn agents for small work; don't fork by habit; don't
resume a stale session; don't write a handoff file where a direct tool-call
returns the result; don't interrupt the human for mechanics.

### Cycle, scope & stop conditions

- **The autonomous unit is whatever scope the founder grants in plain words** —
  a single task, a phase, or a whole epic. The grant *is* the boundary; the
  orchestrator does not narrow or widen it on its own. "Do these 3 phases" →
  run through all 3, then stop. "Do the whole epic" → run every phase and its
  tasks, then stop at epic completion.
- **Within the granted scope, run continuously**: do not yield the turn or ask
  permission between sub-tasks or phases. Decide and execute, delegating per
  the routing policy above.
- **Stop and return to the founder only when:**
  1. the granted scope is complete and verified;
  2. a hard gate is hit — architecture/product decision (domain-contract
     change, irreversible, cross-domain consequence) or merge to `main`;
  3. a real blocker — verification fails and can't be resolved, an ambiguity
     not covered by docs/plan, or missing access/credentials;
  4. a destructive or outward-facing action needs confirmation.
- **Not a stop:** choosing an executor, mechanical sub-tasks, or an
  intermediate red state during a planned architecture-first reset.
- Context-window / compaction handling for very long runs (e.g. a full
  multi-phase epic in one pass) is a **deferred optimization**, not part of
  this process. Build the process first; optimize later.
