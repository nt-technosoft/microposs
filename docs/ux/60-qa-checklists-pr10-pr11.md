# QA Checklists for PR-10 / PR-11

## PR-10 checklist
- typed contracts updated for vacuum model
- no legacy Receipt / InvestorSummary assumptions in active frontend contracts
- stores reflect new backend workflows
- app boots without runtime errors
- route access still coherent by role

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
