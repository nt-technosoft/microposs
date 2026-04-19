# QA Checklists for PR-10 / PR-11

## PR-10 checklist
- typed contracts updated for vacuum model
- no legacy Receipt / InvestorSummary assumptions in active frontend contracts
- stores reflect new backend workflows
- app boots without runtime errors
- route access still coherent by role
- startup sequence from `05-frontend-restart-bootstrap.md` is implemented in order
- canonical routes used (`/procurements/*`, `/investor/procurements/*`) with no legacy aliases in primary nav
- idempotent submit verified for sale create and procurement create

## Startup readiness gate (before broad feature coding)
- [ ] Auth bootstrap works (`token` -> `me` -> role-home)
- [ ] Role-home redirects are deterministic for all 4 roles
- [ ] P0 routes exist and render loading/empty/error/forbidden states
- [ ] Customers screen respects temporary startup policy (cashier read-only)
- [ ] Investor flow uses bridge endpoints (`dashboard`, `procurements`) not legacy summary-only assumptions
- [ ] Route guard and backend permission mismatch cases are documented and produce explicit forbidden UX

## PR-11 checklist
- each critical role has a coherent home flow
- procurement / checkout / return mobile flows are operable on 375px
- loading / empty / error / forbidden states exist on critical screens
- shared patterns remain consistent across modules
- no accidental full redesign drift from foundation layer

## Cross-check
- each primary workflow maps to at least one screen spec
- each screen spec maps to backend contract/store dependencies
- acceptance scenarios exist for owner / cashier / warehouse / investor
