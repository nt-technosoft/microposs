---
name: codex-orchestrator-worker-reviewer
description: Run an approved MicroPOS epic or phase through Codex as an architecture-owning orchestrator, a bounded executor, and a fresh independent reviewer. Use when planning or delivering a cross-domain epic, delegating isolated implementation or audit work, or preparing an implementation slice for review and merge.
---

# MicroPOS Codex Delivery Workflow

Treat `AGENTS.md`, `docs/ROADMAP.md` and the applicable epic as the operating
contract. Read the current code and tests before treating an older discussion as
truth.

## 1. Establish the delivery contract

1. Read the roadmap, the epic and its open questions.
2. For a new or cross-domain slice, use `/plan`; make the target architecture,
   acceptance criteria, dependencies and out-of-scope boundary explicit.
3. When the founder grants a multi-step outcome, create or update `/goal` using
   the same completion criteria. Do not reduce or expand that granted scope.
4. Stop for a founder decision only on an uncovered domain contract,
   irreversibility, cross-domain consequence, missing access, external action or
   merge to `main`.

## 2. Choose the executor

- Implement a small/medium coherent slice directly in the orchestrator thread.
- Use a fresh worker only for a large independent slice, a read-heavy audit or
  truly parallel work. Give it: goal, file/domain boundary, relevant epic
  section, prohibited scope and exact checks.
- Allow one writer per file area. Use a worktree for a long isolated execution
  track. Never use parallel writers as a shortcut.
- Resume a worker only if its context is fresh; otherwise create a fresh worker
  with the current commit, epic task and a compact delta.
- Do not create a handoff file when a direct worker result is available. Use
  `.agents/handoffs/_TEMPLATE.md` only for an unwired external session, a long
  auditable assignment or a durable trace.

## 3. Preserve the target architecture

- Implement the target domain contract, not a shim around legacy behavior.
- Check adjacent effects: inventory/FIFO, finance/GL, suppliers/payables,
  partnerships/profit, reporting, frontend state and Excel replay.
- Keep confirmed financial facts immutable and append-only. Make later
  corrections explicit economic events; do not mutate history to reconcile a
  number.
- Keep business logic in services and cross-domain coordination through the
  established event boundary.

## 4. Run fresh independent review

After the executor validates the slice, start review in a clean context using
app `/review` or CLI `codex exec review`. Supply only:

- the relevant epic/acceptance criteria;
- current diff or commit range;
- test and validation output; and
- explicitly changed boundaries.

Do not pass the executor's chain of thought. Reviewer is read-only and reports
findings ordered by severity, including missing tests and architecture breaches.
The orchestrator owns any follow-up fix and reruns the relevant verification.

## 5. Finish the slice

Update only durable project truth: epic checklist/status, dated decision record
when an architecture choice was made, and roadmap progress when justified. Do
not create duplicate task trackers or session journals.

Finish with outcome, verification, unresolved risk and the next epic task if
the founder-granted scope continues. Do not make the founder relay prompts
between Codex sessions.
