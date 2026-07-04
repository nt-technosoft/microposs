# E22 — Investor-Owned Funds + E21 UX Correction

**Статус:** `IN_REVIEW`
**Прогресс:** 100% implementation
**Зависит от:** E18, E20, E21
**Блокирует:** pilot-ready fund workflow

---

## Цель

Исправить E20/E21 до правильной модели: фонд принадлежит инвестору/управляющему
вне конкретного бизнеса, участники входят через заявки, а бизнес видит фонд в
инвест-договоре только как одного economic holder.

## Контекст и обоснование

E21 зафиксировал investor-led intent, но фактическая реализация всё ещё держала
фонд вокруг tenant `Partner` и business-side money primitives. Это создавало
неправильный UX: фонд выглядел как экран бизнеса, заявка требовала business
partner, а внутренние участники могли просачиваться туда, где бизнесу нужен
только агрегированный фонд.

## Сценарии

- **US-1. Investor creates fund.** Инвестор создаёт фонд без активного business
  tenant; управляющий — его глобальный `InvestmentProfile`.
- **US-2. Public/invite join.** Пользователь открывает фонд по invite/public
  ссылке, видит условия и подаёт заявку без tenant `Partner`.
- **US-3. Manager operations.** Управляющий одобряет заявки, подтверждает
  offline-взносы, меняет terms до deployment и размещает фонд в бизнес-договор.
- **US-4. Business agreement.** Бизнес видит `Фонд: X` как одного инвестора,
  без внутренних участников, заявок и взносов.
- **US-5. Post-receive operations.** После receive приход сначала показывает
  продажи/остаток/recovered capital/profit/loss и доступные действия.

## Текущее состояние

- ✅ **Что уже есть:** E20/E21 lifecycle, hard cap, payout/review/dispute,
  post-receive collapsed source details, investor cabinet routes.
- ⚠️ **Что исправляется:** ownership фонда, API permissions, публичный invite,
  frontend role states, aggregate agreement labels.
- ❌ **Не входит:** full business switcher; MVP остаётся `one owner -> one business`.

## Target contract

- `InvestmentProfile` — глобальная investor identity, не привязанная к бизнесу.
- Fund manager/member/application/contribution используют `InvestmentProfile`;
  legacy `Partner` остаётся только для backfill/старых agreement links.
- Fund fundraising не создаёт business `CashAccount` и не пишет в business GL.
- Fund contribution до deployment — off-ledger append-only факт фонда.
- Deployment создаёт/использует synthetic business-side `Partner` с именем
  `Фонд: X` и заводит вклад фонда в `InvestmentAgreement`.
- `requested_amount`, `approved_amount`, `confirmed_amount` остаются разными
  состояниями.
- Hard cap нельзя превысить без явного terms amendment до первого deployment.
- Первый deployment закрывает новые заявки и взносы.
- Fund API всегда возвращает `viewer_role` и `permissions`.

## План реализации

### Фаза 1 — Backend ownership/API

Добавить `InvestmentProfile`, перевести fund workflow на profile, закрыть
business GL до deployment и ограничить публичный/чужой ответ фонда summary-данными.

### Фаза 2 — Frontend UX

Сделать `/investor/funds` настоящим investor cabinet; join/detail должны
показывать действия по роли, а не по tenant/business контексту.

### Фаза 3 — Agreement/procurement corrections

Agreement detail говорит про investor pool/fund aggregate, procurement после
receive открывается с операционной сводки.

### Фаза 4 — Docs/verification

Отметить E21 tenant-scoped fund path как superseded, добавить roadmap item по
business switcher и прогнать backend/frontend checks.

## Задачи

### Фаза 1
- [x] T-1.1 Добавить `InvestmentProfile`.
- [x] T-1.2 Перевести create/apply/approve/contribute/deploy на profile-first API.
- [x] T-1.3 Убрать fund `CashAccount` на fundraising path.
- [x] T-1.4 Создавать synthetic business holder только на deployment.
- [x] T-1.5 Ограничить публичный/чужой fund response summary-данными.

### Фаза 2
- [x] T-2.1 `/investor/funds`: мои фонды, публичные фонды, action queue, создание.
- [x] T-2.2 Join flow: условия, login/apply, статус заявки.
- [x] T-2.3 Fund detail: manager/member/applicant/public role states.

### Фаза 3
- [x] T-3.1 Agreement detail использует investor pool/fund aggregate label.
- [x] T-3.2 Business видит фонд как `Фонд: X`.
- [x] T-3.3 Post-receive procurement показывает операционную сводку первой.

### Фаза 4
- [x] T-4.1 E21 помечен как superseded для tenant-scoped fund path.
- [x] T-4.2 Roadmap содержит future item: full business switcher.
- [x] T-4.3 Backend targeted + core suite green.
- [x] T-4.4 Frontend type-check/build green.
- [x] T-4.5 Fresh review completed.

## Открытые вопросы

- ✓ Business switcher out of scope для MVP; это future roadmap item.
- ✓ Raw `User` не используем как investor identity: нужен `InvestmentProfile`.
- ✓ Бизнес принимает сам фонд через invest agreement; участников фонда он не
  одобряет и не видит.

## Решённые вопросы (история)

- ✓ 2026-07-04: tenant-scoped fund ownership из E21 superseded; target owner —
  global `InvestmentProfile`.
- ✓ 2026-07-04: business GL получает деньги фонда только на deployment.
- ✓ 2026-07-04: synthetic `Partner` допустим только как business-side holder в
  уже выбранном tenant.
