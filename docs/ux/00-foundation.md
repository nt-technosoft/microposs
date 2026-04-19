# Frontend UX Foundation

## Purpose
Этот слой фиксирует стабильный foundation для PR-10 и PR-11. Он не описывает каждую страницу подробно, а задаёт общие правила, которые должны переиспользоваться во всех модулях.

## Strategy
- **Reuse foundation**: app shell, design tokens, base/shared components, feedback primitives, auth/session backbone, route meta/access semantics.
- **Rewrite feature-domain**: screens, flows, stores, api contracts и adapters, завязанные на legacy `Receipt`, `InvestorSummary`, старые sales/intake сценарии.
- **Не делать full redesign**: визуальный язык эволюционирует, но не сбрасывается.

## Mobile-first principles
- Основной проектный viewport: `375px`.
- Следующие breakpoints: `768 / 1024 / 1440`.
- Приоритет mobile flows: `Receive`, `Checkout`, `Return`.
- Sticky primary CTA на критических экранах.
- Табличное представление — только с `768+`; на mobile приоритет у cards, lists, sections, timelines.

## Visual principles
- Премиальный, спокойный, понятный интерфейс без визуального шума.
- Ключевые действия должны выделяться, но экран не должен превращаться в набор конкурирующих акцентов.
- Shared components и dropdown/select patterns сохраняем как базу качества.
- Lucide icons only; no emoji icons.

## Interaction principles
- Все критические submit-сценарии — idempotent UX: disable during submit, protect from double tap, obvious success/error feedback.
- Обязательные состояния каждого крупного экрана: `loading`, `empty`, `error`, `success`, `forbidden`; при необходимости `offline`.
- Для destructive действий — confirmation pattern.
- Для сложных flows — progressive disclosure, не перегружать экран сразу всеми параметрами.

## Accessibility and usability
- Touch targets минимум `44x44`.
- Понятные labels, не placeholder-only.
- Error message рядом с полем/секцией.
- Цвет не должен быть единственным носителем смысла.
- Respect `prefers-reduced-motion`.

## Shared foundation to preserve
- `frontend/src/main.ts`
- `frontend/src/App.vue`
- `frontend/src/assets/styles/tokens.css`
- `frontend/src/components/base/*`
- `frontend/src/components/feedback/*`
- `frontend/src/router/routes.ts` (route meta / role semantics as idea)

## Primary rewrite targets
- Domain views and flows under `frontend/src/modules/*/views`
- Contracts in `frontend/src/types/*` tied to old model
- API files bound to legacy entities
- Orchestration-heavy stores and router guard behavior tied to old user journeys
