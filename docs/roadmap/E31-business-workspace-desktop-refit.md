# E31 — Business Workspace Desktop Refit

**Статус:** `IN_PROGRESS`
**Прогресс:** 15%
**Зависит от:** Historical Vue data baseline restored on the `e506691` schema
**Блокирует:** —

---

## Цель

Довести существующий Vue Business Workspace до полноценного desktop-first,
task-adaptive интерфейса, сохранив бизнес-логику, API, маршруты, права и
финансовые инварианты. Компактная версия остаётся полноценной по состояниям и
действиям, но больше не диктует композицию рабочих desktop-экранов.

## Границы

- Каноническая поверхность — полный Business Workspace. Ограниченные роли позже
  формируются из тех же маршрутов и действий через существующие permissions.
- В E31 не входят новые backend-контракты, новая продуктовая функциональность,
  объединение страниц и глубокий redesign investor/public/admin.
- React-эксперимент и старый `worktree-desktop-ui` — только источник наблюдений;
  код и архитектура из них не переносятся автоматически.
- Общая локальная БД не используется для acceptance: ветка работает на
  изолированной базе, восстановленной из последнего проверенного Vue dump и
  мигрированной до схемы `e506691`.
- Полная E23-реконструкция U-001 сознательно отложена в отдельную будущую
  задачу и не блокирует presentation-only работу E31.

## Целевой контракт

1. `>=1280px`: фиксированный sidebar `100dvh`, внутренний скролл, закреплённый
   аккаунт и contextual header.
2. `768–1279px`: sticky header и доступный navigation drawer.
3. `<768px`: компактная нижняя навигация из того же route registry.
4. Один state/action contract на всех ширинах; меняется представление, не
   экономическое поведение.
5. `DESIGN.md` и токены задают стартовую deep-emerald/warm палитру и семантику,
   но не обязательные IA, layout, breakpoint или component decisions.
6. Метод E10 «сохранить контракт, пересобрать презентацию» остаётся основным.

## План и чек-лист

### Фаза 0 — изоляция и data gate

- [x] Создать `codex/vue-business-desktop` из `e506691` в отдельном worktree.
- [x] Зафиксировать E31 в roadmap и агентском контракте.
- [x] Создать отдельную PostgreSQL/Redis среду, применить миграции `e506691`.
- [x] Восстановить последний проверенный Vue dump от 2026-06-18 в отдельную БД.
- [x] Применить миграции `e506691`, выполнить smoke-проверки и сверить counts.
- [x] Сохранить локальный untracked post-migrate dump и SHA-256.

### Фаза 1 — app shell

- [ ] Единый typed navigation registry и role filtering.
- [ ] Desktop sidebar, tablet drawer, mobile bottom navigation.
- [ ] Contextual header, account menu, sticky offsets и scroll ownership.
- [ ] Проверка shell на четырёх целевых viewport.

### Фаза 2 — presentation foundation

- [ ] `PageChrome` / `PageContainer`.
- [ ] `ResponsiveOverlay`.
- [ ] `ListWorkbench`.
- [ ] Точечные unit/component tests общих контрактов.

### Фаза 3 — страницы

- [ ] Волна A: sales, products, procurement, agreements, reports.
- [ ] Волна B: history/checkout, finance, reconciliation, transfers,
  categories и payables.
- [ ] Волна C: customers, suppliers, partner management, settings,
  integrations и page map.

### Фаза 4 — сходимость

- [ ] Устранить P0/P1 layout/accessibility/responsive проблемы.
- [ ] Typecheck, lint, build, focused Vitest и browser-smoke ролей.
- [ ] Fresh read-only review и финальный E31 checkpoint.

## Historical Vue baseline — 2026-07-20

- Восстановлен `backups/microposs_excel_demo_2026-06-18.dump`, созданный
  2026-06-18 14:51 и зафиксированный финальным data commit `1ad8a464`.
- Dump содержит последнее проверенное полное Vue-наполнение: 2 бизнеса,
  12 пользователей, 145 товаров и вариантов, 170 партий, 1153 продажи,
  3 прихода и 3 соглашения. Продажи разделены как 491 для Bekzod aka и 662 для
  Uygun aka.
- Dump мигрирован с `partnerships.0032` до `partnerships.0041`; Django check и
  восстановление прошли без ошибок. React-миграции не применялись.
- Post-migrate snapshot хранится локально вне репозитория. Общая база
  `microposs` и React-среда не затронуты.
- Исторический dump содержит три старых расхождения stored status у полностью
  оплаченных `ProcurementTerms`. E31 их не переписывает и не меняет backend:
  это отдельный data-correction вопрос, а не блокер app-shell реконструкции.
- Неуспешный E23 replay и расчёт U-001 сохранены как отдельное исследование, но
  по решению владельца не являются acceptance gate этой UI-итерации.

## Критерии завершения

- Схема и данные воспроизводимы из зафиксированного исторического dump, а
  presentation-only изменения не меняют бизнес-факты и финансовую логику.
- Sidebar не прокручивается вместе со страницей; один маршрут не показывает два
  конкурирующих заголовка; нет горизонтального overflow и console errors.
- Все текущие Business routes доступны, их бизнес-состояния и права не изменены.
- Owner/full-business проверен на `1440×900`, `1280×800`, `1024×768`,
  `390×844`; cashier/warehouse/investor/auth/admin прошли regression-smoke.
- Нет push, PR, deploy или merge.

## Решённые вопросы (история)

- **2026-07-20:** E10 приостановлен как активная UX-директива и заменён E31.
  Завершённые экраны E10 и метод «сохранить контракт, пересобрать презентацию»
  остаются полезным evidence, но mobile-first и жёсткий layout-канон не
  переносятся.
- **2026-07-20:** общий `microposs` не откатывается. Dump от 2026-06-18
  восстановлен в отдельную базу и мигрирован до схемы `e506691`; это текущий
  reproducible UI baseline. Полная E23-реконструкция отложена.
- **2026-07-20:** synthetic contribution, неутверждённый date shift и скрытый
  обход payout policy запрещены как способы закрыть U-001 data gate.
