# Open Decisions and Conflicts

## Purpose
Зафиксировать не догадки, а реальные конфликты между текущими role rules, routes, UX-spec и target frontend architecture, чтобы clean-slate rewrite не принимал скрытые решения молча.

## Confirmed conflicts

### CONF-001 — Customers / Receivables: owner-only vs cashier-operational
- `role-matrix.md` currently states customers write/pay is owner-only.
- UX specs and role/journey design expect cashier to use customer debt flow operationally.
- Affected screens/widgets:
  - `SCN-CSH-007`
  - receivable/payment actions
- Resolution needed before final implementation policy is frozen.

### CONF-002 — Investor scope wording still legacy in role matrix
- `role-matrix.md` still describes investor scope as `Investor summaries/profit records only`.
- Current target architecture is procurement/ledger-centric investor cabinet.
- This must be updated so frontend and backend scope use the same language.

### CONF-003 — Owner Dashboard vs Reports Dashboard boundary
- Current UX docs describe both `SCN-OWN-001` owner dashboard and `SCN-OWN-001R` reports dashboard.
- Need explicit division of responsibilities:
  - action-oriented launchpad vs analytic/reporting surface.

### CONF-004 — Legacy route aliases vs target route language
- Current runtime may temporarily expose `/intake/*` and `/investor/contracts/:id` aliases.
- Target UX wants `/procurements/*` and `/investor/procurements/:id`.
- Aliases are transitional, not target architecture.

## Recommended rule for implementation
Until conflicts are explicitly resolved:
- implement no hidden permission escalation,
- prefer target naming in UX docs,
- keep conflict notes close to affected screens,
- avoid treating aliases as final product architecture.
