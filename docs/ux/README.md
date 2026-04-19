# Frontend UX Documentation Layer

## Purpose
Этот слой отделяет UX / frontend functional specification от стратегических и архитектурных документов. Он нужен для качественной реализации PR-10 и PR-11 без потери роли, сценариев, экранов, виджетов и требований.

## Document map
- `00-foundation.md` — визуальные и interaction principles, reuse/rewrite strategy
- `10-navigation-and-roles.md` — role map, workflows, initial screen inventory
- `15-route-screen-matrix.md` — explicit route ↔ role ↔ screen ↔ view ↔ contract map
- `16-open-decisions-and-conflicts.md` — explicit contradictions and unresolved policy decisions
- `17-spec-completeness-status.md` — readiness level and what still needs detailing
- `18-foundation-keep-delete-plan.md` — explicit foundation / reference / delete map for clean-slate rewrite
- `20-pages/` — page specifications
- `30-components/` — widget/component specifications
- `40-copy-i18n.md` — copy rules, terminology, i18n guidance
- `50-state-api-contracts.md` — contract/store/backend dependency layer
- `50-pr10-contract-map.md` — exact migration map for types/api/stores before PR-10
- `60-qa-checklists-pr10-pr11.md` — QA and acceptance skeleton
- `70-traceability-matrix.md` — role → journey → screen ↔ widget ↔ requirement mapping

## How to use
1. Сначала role/workflow map
2. Потом route-screen map
3. Потом page specs
4. Потом component specs
5. Потом contract/state alignment
6. Потом QA/acceptance linking

## Governance
- Нормативные документы не превращаем в UX-помойку.
- Этот слой хранит проверяемые требования, а не чат-заметки.
- Спорные решения выносятся в отдельные decision notes внутри соответствующих spec-файлов.
- Legacy route names и aliases не считаются целевой архитектурой, если это не подтверждено отдельным решением.
