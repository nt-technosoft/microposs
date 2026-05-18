# Frontend — Vue 3 Архитектура

## Структура проекта

```
frontend/src/
├── api/            HTTP-клиенты (типизированные)
│   ├── client.ts   axios + interceptors + AbortController
│   ├── finance.ts  finance domain API
│   ├── catalog.ts
│   ├── inventory.ts
│   ├── sales.ts
│   ├── customers.ts
│   ├── suppliers.ts
│   └── ...
├── stores/         Pinia-сторы (один per domain)
│   ├── auth.ts
│   ├── session.ts  POS-сессия
│   ├── products.ts
│   ├── cart.ts
│   └── ui.ts
├── modules/        Feature-модули
│   ├── auth/
│   ├── sales/
│   ├── products/
│   ├── intake/         Procurement/приёмка
│   ├── inventory/
│   ├── reports/
│   ├── investors/
│   └── finance/
├── components/     Shared-компоненты
├── composables/    Переиспользуемая логика
│   ├── useToast.ts
│   ├── useFxRate.ts
│   └── ...
├── i18n/           Переводы интерфейса ru / uz / en
│   ├── index.ts
│   ├── keys.ts
│   └── locales/
├── router/
│   ├── index.ts    router + auth guard
│   └── routes.ts   маршруты с meta (roles, layout)
└── utils/          currency formatting, dates
```

---

## Модульная структура

Каждый `modules/<domain>` содержит:
```
modules/sales/
├── views/          Страницы (Vue Router)
├── components/     Domain-специфичные компоненты
└── (stores/)       Если нужен отдельный стор
```

---

## Shared UI-компоненты

Перед созданием нового поля или селекта проверяй `src/components/`.

- Для суммы с переключением валюты используй `src/components/forms/MoneyCurrencyInput.vue`. Не собирай заново отдельный `input + currency select/button` внутри доменных экранов.
- Для выбора из короткого списка используй `src/components/base/BaseSelect.vue`, особенно на mobile-first экранах. Он даёт единый trigger и bottom-sheet вместо браузерного select.
- Если один и тот же паттерн повторяется в 2-3 местах, выноси его в `src/components/base`, `src/components/forms` или `src/components/feedback`.
- Domain-компоненты в `modules/<domain>/components` должны отвечать за бизнес-сценарий, а не переизобретать базовые контролы.
- Старые intake/procurement компоненты можно использовать как UX-reference, но новый общий UI-паттерн должен жить в shared-компонентах.

---

## API-слой

### `src/api/client.ts`
- Axios-инстанс с `baseURL = '/'` (proxy через Vite)
- Request interceptor: добавляет `Authorization: Bearer <token>`
- Response interceptor: `axios.isCancel(error)` → тихо игнорирует cancelled-запросы; другие ошибки → пробрасывает

**`createAbortController()`** — утилита для создания `AbortController`.

### Паттерн для отменяемых запросов
```typescript
let _abort: AbortController | null = null

async function load() {
  _abort?.abort()
  _abort = new AbortController()
  const data = await fetchSomething(params, _abort.signal)
}

onBeforeUnmount(() => {
  _abort?.abort()
})
```

### Типизированные API-функции
Все функции в `src/api/` возвращают `Promise<TypedResponse>`. Интерфейсы экспортируются вместе с функциями.

**Пример (`finance.ts`):**
```typescript
export interface ReportSummaryResponse {
  is_computing: boolean
  daily_summary: DailySummary[]
  cash_flow: CashFlowItem[]
  debt: DebtSummaryItem[]
  parity: { payables, stock, trial_balance, cash_accounts }
}

export async function fetchReportSummary(
  params?: FetchReportSummaryParams,
  signal?: AbortSignal,
): Promise<ReportSummaryResponse> { ... }
```

---

## Pinia-сторы

### `useAuthStore`
- `token`, `user`, `role`, `userLoaded`
- `ensureUserLoaded()` — загружает пользователя если не загружен
- `logout()` — очищает стейт и localStorage

### `useSessionStore`
- `currentSession: PosSession | null`
- `loadCurrentSession()` — запрашивает открытую сессию
- Cooldown 30 секунд между загрузками (защита от flood при навигации)

### `useProductsStore`
- `items`, `categories`, `search`, `loading`
- Debounce 300мс на поиск (модульный таймер, не в state)
- `setSearch(query)` — обновляет поиск с debounce

### `useCartStore`
- Корзина продажи: `lines[]`, `payments[]`
- `addLine`, `removeLine`, `setQuantity`, `submit` (→ `create_sale`)

### `useUIStore`
- `simpleSellerMode` — режим упрощённого кассира (только `/sales`)
- `locale` — язык интерфейса (`ru`, `uz`, `en`), синхронизируется с `vue-i18n` и `localStorage`

---

## Локализация

Frontend использует `vue-i18n`. Русский — базовый язык и fallback, узбекский — латиницей.

### Структура
```
src/i18n/
├── index.ts              # createI18n, messages, setI18nLocale()
├── keys.ts               # Locale, supportedLocales, fallbackLocale
└── locales/
    ├── ru.ts             # исходный смысловой текст
    ├── uz.ts             # смысловой перевод на O‘zbekcha
    └── en.ts             # смысловой перевод на English
```

### Правила ключей
- Ключи группируются по смысловым доменам: `common`, `nav`, `sales`, `products`, `procurements`, `reports`, `investors`, `settings`.
- Общие действия хранятся в `common`, но контекстные тексты остаются внутри домена.
- Не использовать дословный перевод, если он ломает мобильный UI или звучит не как продуктовый интерфейс.
- Новые UI-тексты добавлять сразу во все три файла. `uz.ts` и `en.ts` типизированы от `ru.ts`, поэтому пропущенные ключи ловятся `vue-tsc`.

### Хранение языка
- До входа язык хранится в `localStorage` (`microposs_locale`).
- После входа `/api/v1/auth/me/` возвращает `locale`.
- Настройки сохраняют язык через `/api/v1/auth/preferences/`.
- `Accept-Language` отправляется во все API-запросы.

### Что не переводим автоматически
- Названия товаров, категорий, поставщиков, покупателей и складов, если их ввёл пользователь.
- Системные fallback-значения вроде `Main Store` нормализуются через label helpers.

---

## Router

### Auth Guard (`router/index.ts`)

```
beforeEach:
1. Если requiresAuth && нет токена → redirect /login
2. Если токен && !userLoaded → await auth.ensureUserLoaded()
3. Если /login && токен → redirect getRoleHomeRoute(role)
4. Если роль не входит в meta.roles → redirect getRoleHomeRoute(role)
5. Если simpleSellerMode && owner/cashier → принудительно /sales
```

### Маршрут meta

```typescript
{
  requiresAuth: true,          // по умолчанию true
  roles: ['owner', 'cashier'], // пустой массив = все аутентифицированные
  layout: 'default' | 'blank' | 'investor',
}
```

### Начальные маршруты по ролям

| Роль | Стартовая страница |
|---|---|
| `platform_admin` | `/platform/requests` |
| `investor` | `/investor/dashboard` |
| `warehouse` | `/procurements` |
| `owner` / `cashier` | `/sales` |

---

## Ключевые паттерны

### Debounce для FX-переключения
```typescript
let _currencyTimer: ReturnType<typeof setTimeout> | null = null

function setReportCurrency(currency: ReportCurrency) {
  reportCurrency.value = currency
  if (_currencyTimer !== null) clearTimeout(_currencyTimer)
  _currencyTimer = setTimeout(() => {
    _currencyTimer = null
    loadAnalytics()
  }, 300)
}
```

### is_computing polling (Reports Dashboard)
```typescript
if (result.is_computing) {
  let attempts = 0
  _computingPollTimer = setInterval(async () => {
    attempts++
    if (attempts > 12) { clearInterval(_computingPollTimer!); return }
    const poll = await fetchReportSummary(range)
    if (!poll.is_computing) {
      clearInterval(_computingPollTimer!)
      applySummaryResult(poll)
      isComputing.value = false
    }
  }, 5000)
}
```

### extractList utility
Принимает `PaginatedResponse<T> | T[]` → возвращает `T[]`. Используется для безопасного разворачивания пагинированных и непагинированных ответов.

---

## Дизайн-система

- **Точки останова:** 375px → 768px → 1024px → 1440px (mobile-first)
- **Дизайн-токены:** CSS custom properties в `src/assets/tokens.css`
- **Иконки:** Lucide Vue Next (никаких эмодзи как структурных иконок)
- **Анимации:** 150–300мс; `prefers-reduced-motion` поддерживается
- **Компоненты:** `<script setup>` + Composition API везде

---

## Ключевые composables

### `useFxRate()`
- Загружает последний курс USD/UZS для дашборда
- `rate`, `error`, `load`

### `useToast()`
- `toast.success(message)`, `toast.error(message)`, `toast.info(message)`
- Авто-скрытие через 3–5 сек

### `formatPrice(amount, currency, fxRate?)`
- Форматирует сумму с учётом валюты и курса
- `UZS` → `1 200 000 UZS`, `USD` → `$123.45`

---

## Модуль Reports Dashboard

Ключевой экран с комбинированной загрузкой данных.

**Загрузка:**
- `loadSummary()` → `fetchReportSummary()` (1 запрос вместо 5)
- `loadAnalytics()` → `fetchReportAnalytics()` (1 запрос вместо 3)
- `loadAll()` = `Promise.all([loadSummary(), loadAnalytics()])` = **2 запроса вместо 10**

**Периоды:** today / week / month / all / custom

**Переключение валюты (UZS/USD):**
- Дебаунс 300мс
- Только `loadAnalytics()` перезапрашивается (summary не зависит от валюты)

**AbortController:**
- `_summaryAbort` и `_analyticsAbort` отменяют in-flight запросы при смене параметров или unmount
- `CanceledError` — тихо игнорируется в catch-блоках
