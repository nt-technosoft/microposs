# MicroPOS / Sherik POS — Operating Contract for Codex and Other Agents

MicroPOS is a task-adaptive financial-partnership layer for retail businesses:
Mudaraba, Musharaka, consignment, multi-location and multi-currency. It is not
another POS: it records the economic terms of a partnership, fixes factual
capital snapshots at receipt, and makes FIFO profit/loss distribution auditable.

## Source of truth and reading order

1. `docs/ROADMAP.md` — live priority and status.
2. The applicable `docs/roadmap/E*.md` — scope, decisions, checklist and open
   questions for the epic.
3. `CLAUDE.md` — canonical key business rules and detailed project rationale.
4. Domain docs, tests and current code — current implementation truth.

Do not infer current priority from this file. Do not duplicate a business rule
from `CLAUDE.md`: link to its canonical place instead. If sources conflict,
resolve the conflict explicitly in the relevant epic before changing behavior.

## Collaboration contract

Work as a technical co-founder: assess ideas, identify a cleaner alternative
where one exists, and then execute the agreed direction without routine
permission checks. Do not add infrastructure, abstractions, documents or tests
without a concrete product or architecture need.

An explicit founder grant defines autonomous scope: one task, one phase or an
entire epic. Complete it continuously. Return only when the granted scope is
complete and verified, or when there is a genuine gate:

- a domain-contract or irreversible decision;
- a cross-domain consequence not covered by the epic;
- a failing verification that cannot be resolved locally;
- missing access/credentials; or
- destructive, external-facing or `main`-merge action.

Choosing a tool, a worker or a mechanical implementation detail is not a gate.
Never make the founder a prompt courier between agents.

## Architecture-first delivery

For a foundational feature or a domain rewrite, design the target contract
first and apply its delta to the existing system. Do not preserve legacy UI,
tests, shims or aliases merely because they are locally green.

- Resolve conflicts at a domain boundary, not with compatibility patches.
- Check impact on inventory/FIFO, finance/GL, suppliers/payables,
  partnerships/profit, reporting, frontend state and Excel replay.
- Financial records are immutable after confirmation; cross-domain business
  communication goes through services and `OutboxEvent`.
- Verify target behavior. A green legacy suite is insufficient if it encodes an
  obsolete model.
- A planned intermediate red state is acceptable; an undocumented divergence
  from the target architecture is not.

## Codex delivery loop

Use `/plan` for a new or cross-domain epic. Turn the agreed scope and done
criteria into the epic before implementation. Use `/goal` when the user has
granted a multi-step outcome and keep the objective tied to those criteria.

| Role | Responsibility | Boundary |
|---|---|---|
| **Orchestrator** | Read the roadmap/epic, choose the execution route, preserve architecture and decide whether a real founder gate exists. | One main Codex goal thread. |
| **Executor** | Implement an approved bounded slice and validate it. | One owner writes a file area at a time. |
| **Reviewer** | Find defects against the epic, diff and tests. | Fresh context, read-only; never the executor reviewing its own reasoning. |

Route work once per phase, not once per message:

1. Do a small or medium bounded slice directly in the main thread.
2. Delegate only a large independent slice, a read-heavy audit, or genuinely
   parallel work. Give each worker a precise outcome, boundaries and checks.
3. Never run concurrent writers in the same files. Use a worktree for a long or
   isolated implementation track.
4. Resume a worker only while its context remains fresh; otherwise start a fresh
   worker with a compact delta from the epic and git state.
5. Use independent review where risk justifies it. For E31 it is required after
   the shared shell and before final convergence, not after every page slice.
   Give the reviewer the epic, diff, criteria and verification output — not the
   executor's private reasoning.
6. Handoff files under `.agents/handoffs/` are fallback only for an unwired
   external session, a long auditable task or durable trace. Follow its template.

The reviewer reports findings first. The orchestrator decides fixes and reruns
relevant checks. Ordinary bounded UI slices may finish with proportional local
verification; a reviewer never writes production changes unless separately
assigned as executor.

## Git and worktree hygiene

- Keep the repository root as the clean checkout of the current integration
  branch. Do not place experiments or linked worktrees in tracked directories.
- Every isolated track uses a purpose-named `codex/<topic>` branch and a linked
  worktree under ignored `/.worktrees/<topic>` (or a sibling directory). Never
  use `/.claude/worktrees/`, anonymous names such as `work3`, or add a worktree
  path to the index as a gitlink.
- A worktree is a disposable checkout, not the only copy of work. Before pausing
  or removing it, commit meaningful changes to its branch. Remove clean inactive
  worktrees while retaining their branches so they can be recreated later.
- `node_modules`, build output, caches and browser-test screenshots are
  reproducible artifacts. Keep them ignored and never copy them into the root
  checkout as a way to preserve an experiment.
- Before merge or handoff, inspect `git worktree list` and `git status` in every
  retained worktree. If unrelated dirty work exists, checkpoint it on a dedicated
  archive branch before cleaning the integration checkout.

## Documentation discipline

- New large direction → one epic based on `docs/roadmap/_template.md` plus a
  roadmap entry.
- Architectural decision affecting more than one domain/file → dated entry in
  the epic's `Решённые вопросы (история)`; use a dedicated architecture doc only
  for a lasting cross-cutting invariant.
- When reversing a decision, mark the old decision as superseded and record the
  replacement with date and rationale. Do not silently rewrite history.
- Do not create journals, progress notes, duplicate task lists or handoffs for
  normal inline agent work. Git history and epic checklists carry execution state.

## Domain and code conventions

- Backend: Django 5 / PostgreSQL / Redis / Celery; frontend: Vue 3,
  TypeScript, Pinia, Vue Router, Vite.
- All models inherit `core.BaseModel`; business data is tenant-scoped.
- Financial POST operations accept `client_request_id` for idempotency.
- Domain services own business logic. Foreign keys may cross domains, but
  domain logic must not directly import another domain's models.
- Use append-only economic events and derived read models; never mutate
  confirmed financial history to make a later number fit.
- Frontend follows the active epic. In E31, data-dense Business Workspace flows
  are desktop-first and compact screens preserve the same states and actions.
  Use Composition API, typed clients in `src/api/`, domain stores, shared
  controls, Lucide icons and 150–300ms accessible motion.
- Apply `.agents/skills/microposs-frontend-design/SKILL.md` for product UI.
  Generic `frontend-skill` is optional and mainly relevant to public/marketing
  surfaces; it is not an authority over operational IA.

## Navigation and verification

| Domain | Backend | Frontend |
|---|---|---|
| Inventory / Lots / FIFO | `apps/inventory/services.py` | `src/modules/inventory/` |
| Procurement / receipt | `apps/partnerships/services.py` | `src/modules/intake/` |
| Sales / POS / returns | `apps/sales/services.py` | `src/modules/sales/` |
| Finance / accounting | `apps/finance/services.py` | `src/modules/finance/` |
| Partnerships / profit | `apps/partnerships/services.py` | `src/modules/investors/` |
| Reporting | `apps/finance/views.py` | `src/modules/reports/` |

Graphify is an optional navigation aid for unfamiliar or cross-module areas,
not a required first step and never a source of truth. Prefer ordinary targeted
search and source reading when they are sufficient. Treat Graphify `INFERRED`
edges and ambiguous symbol paths as leads only; confirm them in code, tests and
domain docs before making a conclusion. Default rebuild:
`.graphify-venv/bin/graphify update .`.

Run checks proportionate to the change. For backend/domain work, the baseline is:

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m pytest apps/core/tests/ -q
```

For Excel replay use only `docs/testing-data-workflow.md` and its canonical
snapshot commands. Do not insert final spreadsheet totals directly into reports.

## Completion report

For implementation work, report only outcome, verification, unresolved risk and
the next concrete task if scope remains. Do not paste diffs or file inventories.
Respect explicit constraints such as no commit, no UI behavior change or a
strict file boundary.
