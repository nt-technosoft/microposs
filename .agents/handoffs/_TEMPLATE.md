# Handoff: <id> — <title>

> Fallback only. Use a handoff file ONLY when (a) an external session is not
> wired to the orchestrator, (b) a long-running task needs a durable trace, or
> (c) the assignment/result must be auditable. If a direct tool-call (subagent
> or Codex plugin) returns the result inline, do NOT create this file.

Epic: docs/roadmap/E1X-*.md   Branch/worktree: <branch>
Role: implementer | reviewer | ui | explorer
Model hint: opusplan | sonnet-exec | codex

## Goal
1–3 lines: what must exist at the end.

## Context (only what is NOT derivable from docs + git log)
- <delta fact>

## Constraints
- Key Business Rules apply; specifically: #<n> (only if relevant)
- architecture-first: target, not shim

## Done =
- [ ] <verifiable criterion>
- [ ] tests: <command>

## Out of scope
- <what NOT to touch>

---

## Result — <agent/model> — <date>
Status: done | blocked | needs-decision
Branch/commit: <hash>

### What was done
- <claim → file/area> (no diff dumps)

### Verification
- <command> → <result: pass/fail + numbers>

### Risks / open
- <risk or question for Opus/founder>

### Next
- <proposed next step>
