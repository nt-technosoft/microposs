# E31 — Business Workspace Desktop Refit

**Статус:** `IN_PROGRESS`
**Прогресс:** 5%
**Зависит от:** E23-compatible data baseline
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
  изолированной базе со схемой и фактами, совместимыми с `e506691`.

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
- [ ] Выполнить Sherik Excel Replay и доказать E23/FIFO/GL/payable инварианты.
- [ ] Сохранить локальный untracked custom dump, SHA-256 и source manifest.

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

## Data gate — 2026-07-20

- Fresh schema успешно мигрирована до `partnerships.0041`; React-миграции не
  применялись. Семь workbook sources зафиксированы локальным SHA-256 manifest.
- Dry-run: 7 master / 6 local deals, 205 reconstructed transfers, 20 warnings,
  0 blockers. Targeted E18/E23 suite: 48 tests passed.
- Реальный apply транзакционно остановился на `U-001`: приходу от
  `2026-02-08` нужно 105.20 USD investor-side extra capital, при этом eligible
  recovered proceeds составляют только 59.44 USD. Записи replay откатились;
  общая БД не затронута.
- Корень: общий `apply_credit_term_receive_deferrals()` без отдельного решения
  переносит 81 COD/NASIYA строку на дату первой продажи. Для строк 9/52/53/60
  это создаёт неподтверждённую февральскую потребность в капитале. Утверждённые
  source corrections U-001 этих переносов не содержат.
- Дополнительно полный U-001 требует 21,491,409.44 UZS investor profit
  capitalization и явное изменение условий; E23 намеренно не разрешает
  generic `CAPITALIZE_PROFIT`.

До продуктового решения UI-фазы остановлены. Корректный путь — отдельный E23
slice с явным schedule и terms/amendment. Допустимый временный путь для E31 —
отдельная явно неполная UI-база без U-001; она не является canonical investor
baseline и не может использоваться для проверки Uygun/инвесторских расчётов.

## Критерии завершения

- Схема и данные воспроизводимы из зафиксированных источников и проходят E23,
  FIFO, GL/pool/cash и payable проверки.
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
- **2026-07-20:** общий `microposs` не откатывается. Dump от 2026-06-18 остаётся
  историческим reference; acceptance-база строится replay-путём на отдельной
  схеме `e506691`.
- **2026-07-20:** synthetic contribution, неутверждённый date shift и скрытый
  обход payout policy запрещены как способы закрыть U-001 data gate.
