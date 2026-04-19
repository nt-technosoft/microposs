# Open Decisions and Conflicts

## Purpose
Зафиксировать не догадки, а реальные конфликты между текущими role rules, routes, UX-spec и target frontend architecture, чтобы clean-slate rewrite не принимал скрытые решения молча.

## Confirmed conflicts

### CONF-001 — Customers / Receivables: owner-only vs cashier-operational
- `docs/role-matrix.md` still states customers write/pay is owner-only.
- Backend currently allows cashier read (`GET`) and owner-only write/pay (`POST`) in `backend/apps/customers/views.py`.
- UX specs expect cashier-operational receivable flow in `SCN-CSH-007`.
- **Startup decision (temporary, normative):** for restart P0/P1 keep cashier read-only in customers; owner executes pay/create until policy is explicitly changed.
- Resolution needed before final receivable UX policy is frozen.

### CONF-002 — Investor scope wording still legacy in role matrix
- `docs/role-matrix.md` still describes investor scope as `Investor summaries/profit records only`.
- Backend investor bridge already exposes `/api/v1/investors/dashboard/` and `/api/v1/investors/procurements/*`.
- Current target architecture is procurement/ledger-centric investor cabinet.
- This must be updated so role matrix and restart docs use the same language.
### CONF-003 — Owner Dashboard vs Reports Dashboard boundary
- Current UX docs describe both `SCN-OWN-001` owner dashboard and `SCN-OWN-001R` reports dashboard.
- **Startup decision (normative):** owner dashboard is the action-oriented launchpad; reports dashboard is the analytic/reporting surface.
- Do not merge these surfaces in P0/P1. Keep reports outside startup-critical scope.

### CONF-004 — Legacy route aliases vs target route language
- Current runtime may temporarily expose `/intake/*` and `/investor/contracts/:id` aliases.
- Target UX wants `/procurements/*` and `/investor/procurements/:id`.
- **Startup decision (normative):** aliases are transitional redirect-only routes; canonical route names and navigation labels must use procurements terminology.
- Aliases are transitional, not target architecture.

### CONF-005 — Investor payout history / aggregate ledger backend shape
- Current UX expects payout-history and ledger-centric investor surfaces, but backend endpoint shape may still evolve.
- **Startup decision (normative):** do not block frontend restart on final payout-history aggregation design.
- Treat payout-history / aggregate ledger shape as P1 backend-alignment work; keep investor P0 focused on dashboard + procurements list + procurement detail.

### CONF-006 — Separate `/receiving` route vs filtered procurements flow
- Receiving can be modeled either as a dedicated route or as a filtered/stateful branch of procurement detail/list flows.
- **Startup decision (normative):** do not create separate `/receiving` route in P0.
- Receiving behavior lives under `/procurements` and `/procurements/:id` until dedicated route value is proven.

## Recommended rule for implementation
Until conflicts are explicitly resolved:
- implement no hidden permission escalation,
- prefer target naming in UX docs,
- keep conflict notes close to affected screens,
- avoid treating aliases as final product architecture,
- avoid expanding P0 scope to resolve non-critical information architecture questions.
