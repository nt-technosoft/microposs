<script setup lang="ts">
import { ref, computed } from 'vue'
import { cn } from '@/lib/utils'

type Lang = 'ru' | 'en' | 'uz'
const lang = ref<Lang>('ru')
const LANGS: { code: Lang; label: string }[] = [
  { code: 'ru', label: 'Рус' },
  { code: 'en', label: 'Eng' },
  { code: 'uz', label: "O'zb" },
]

// Environment values (language-neutral)
const ENV = {
  app: 'https://sherik.nt-technosoft.uz/',
  server: '84.247.166.45',
  keys: 'https://sherik.nt-technosoft.uz/settings/integrations',
  user: 'owner / Owner123!',
}
const BASE = 'https://sherik.nt-technosoft.uz/api/v1/integrations/yespos/v1/'

const HEADERS = [
  { name: 'X-Integration-Key', value: 'ssk_yespos_live_...', when: { ru: 'всегда', en: 'always', uz: 'har doim' } },
  { name: 'Content-Type', value: 'application/json', when: { ru: 'для POST', en: 'for POST', uz: 'POST uchun' } },
  { name: 'X-Request-Id', value: '<id>', when: { ru: 'опц., идемпотентность POST', en: 'optional, POST idempotency', uz: 'ixtiyoriy, POST idempotensiyasi' } },
]

const ENDPOINTS = [
  { method: 'POST', path: '/sale', purpose: { ru: 'Событие продажи', en: 'Sale event', uz: 'Sotuv hodisasi' } },
  { method: 'POST', path: '/inventory', purpose: { ru: 'Событие по остаткам', en: 'Inventory event', uz: 'Qoldiqlar hodisasi' } },
  { method: 'POST', path: '/agreement-link', purpose: { ru: 'Событие по договору', en: 'Agreement event', uz: 'Shartnoma hodisasi' } },
  { method: 'POST', path: '/{slug}', purpose: { ru: 'Произвольное событие (slug: [a-z0-9-], ≤64)', en: 'Custom event (slug: [a-z0-9-], ≤64)', uz: 'Ixtiyoriy hodisa (slug: [a-z0-9-], ≤64)' } },
  { method: 'GET', path: '/agreements', purpose: { ru: 'Список активных инвест-договоров', en: 'List active investment agreements', uz: "Faol investitsiya shartnomalari ro'yxati" } },
]

const RESPONSES = [
  { code: '201', body: '{"id":"...","status":"received"}', meaning: { ru: 'принято', en: 'accepted', uz: 'qabul qilindi' } },
  { code: '200', body: '{"status":"duplicate"}', meaning: { ru: 'повтор по X-Request-Id', en: 'repeat of same X-Request-Id', uz: 'bir xil X-Request-Id takrori' } },
  { code: '400', body: '{"detail":"..."}', meaning: { ru: 'неверный slug (только /{slug})', en: 'invalid slug (only /{slug})', uz: "noto'g'ri slug (faqat /{slug})" } },
  { code: '401', body: '{"detail":"..."}', meaning: { ru: 'нет/неверный/отозванный ключ или IP не разрешён', en: 'missing/invalid/revoked key, or IP not allowed', uz: "kalit yo'q/noto'g'ri/bekor qilingan yoki IP ruxsat etilmagan" } },
]

const T: Record<Lang, Record<string, string>> = {
  ru: {
    title: 'API интеграции (YesPos)',
    env: 'Окружение', envApp: 'Приложение', envServer: 'Сервер (IP)', envKeys: 'Управление ключами', envUser: 'Тестовый пользователь',
    base: 'База', headers: 'Заголовки', colHeader: 'Заголовок', colValue: 'Значение', colWhen: 'Когда',
    keyNote: 'Ключ создаётся в приложении: Настройки → Интеграции → Добавить ключ (показывается один раз). Отзыв ключа сразу делает его недействительным.',
    endpoints: 'Эндпоинты', colMethod: 'Метод', colPath: 'Путь', colPurpose: 'Назначение',
    bodyNote: 'Тело POST — произвольный JSON-объект (сохраняется целиком).',
    how: 'Принцип работы (текущая фаза)',
    howP1: 'Сейчас эндпоинты только принимают запросы по указанным путям и сохраняют тело целиком (raw). Обработки и валидации структуры пока нет.',
    howP2: 'Присылайте разные виды запросов на соответствующие пути. Как только получим реальную структуру и форматы данных — зафиксируем контракт и построим логику обработки на их основе.',
    responses: 'Ответы', colCode: 'Код', colBody: 'Тело', colMeaning: 'Значение',
    agg: 'GET /agreements → массив объектов: id, title, investor_name, profit_ratio, capital_amount, currency, status.',
    security: 'Безопасность',
    securityP: 'Ключ передавать только по HTTPS. Для ключа можно задать allowlist по IP. Ключ в Git/логи не коммитить.',
  },
  en: {
    title: 'Integration API (YesPos)',
    env: 'Environment', envApp: 'App', envServer: 'Server (IP)', envKeys: 'Key management', envUser: 'Test user',
    base: 'Base', headers: 'Headers', colHeader: 'Header', colValue: 'Value', colWhen: 'When',
    keyNote: 'The key is created in the app: Settings → Integrations → Add key (shown once). Revoking a key makes it invalid immediately.',
    endpoints: 'Endpoints', colMethod: 'Method', colPath: 'Path', colPurpose: 'Purpose',
    bodyNote: 'POST body is an arbitrary JSON object (stored as-is).',
    how: 'How it works (current phase)',
    howP1: 'For now the endpoints only accept requests on the given paths and store the full body as-is (raw). There is no processing or schema validation yet.',
    howP2: 'Send the different request types to the matching paths. Once we have the real structure and formats of your data, we will lock the contract and build the processing logic on top of it.',
    responses: 'Responses', colCode: 'Code', colBody: 'Body', colMeaning: 'Meaning',
    agg: 'GET /agreements → array of objects: id, title, investor_name, profit_ratio, capital_amount, currency, status.',
    security: 'Security',
    securityP: 'Send the key over HTTPS only. A per-key IP allowlist is supported. Never commit the key to Git/logs.',
  },
  uz: {
    title: 'Integratsiya API (YesPos)',
    env: 'Muhit', envApp: 'Ilova', envServer: 'Server (IP)', envKeys: 'Kalitlarni boshqarish', envUser: 'Test foydalanuvchi',
    base: 'Manzil', headers: 'Sarlavhalar', colHeader: 'Sarlavha', colValue: 'Qiymat', colWhen: 'Qachon',
    keyNote: "Kalit ilovada yaratiladi: Sozlamalar → Integratsiyalar → Kalit qo'shish (bir marta ko'rsatiladi). Kalitni bekor qilish uni darhol yaroqsiz qiladi.",
    endpoints: 'Endpointlar', colMethod: 'Metod', colPath: "Yo'l", colPurpose: 'Maqsad',
    bodyNote: "POST tanasi — ixtiyoriy JSON obyekt (to'liq saqlanadi).",
    how: 'Qanday ishlaydi (joriy bosqich)',
    howP1: "Hozircha endpointlar so'rovlarni faqat qabul qiladi va tanasini to'liq (raw) saqlaydi. Hali ishlov berish yoki struktura tekshiruvi yo'q.",
    howP2: "Turli xil so'rovlarni mos yo'llarga yuboring. Ma'lumotlarning haqiqiy strukturasi va formatlarini olganimizdan so'ng, shartnomani belgilaymiz va shu asosda ishlov berish mantig'ini quramiz.",
    responses: 'Javoblar', colCode: 'Kod', colBody: 'Tana', colMeaning: "Ma'no",
    agg: 'GET /agreements → obyektlar massivi: id, title, investor_name, profit_ratio, capital_amount, currency, status.',
    security: 'Xavfsizlik',
    securityP: "Kalitni faqat HTTPS orqali yuboring. Kalit uchun IP allowlist qo'llab-quvvatlanadi. Kalitni Git/loglarga joylashtirmang.",
  },
}

const t = computed(() => T[lang.value])
const labelCls = 'text-xs font-bold uppercase tracking-wide text-green-700'
const thCls = 'px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-neutral-600'
const tdCls = 'px-3 py-2.5 align-top text-sm text-foreground'
</script>

<template>
  <div class="min-h-screen bg-neutral-100">
    <div class="mx-auto max-w-[760px] px-4 py-8">
      <!-- Header + language switch -->
      <header class="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-[16px] bg-primary px-5 py-5 text-white shadow-sm">
        <h1 class="text-2xl font-bold text-white">{{ t.title }}</h1>
        <div class="flex rounded-[10px] bg-white/15 p-1">
          <button
            v-for="l in LANGS"
            :key="l.code"
            type="button"
            :class="cn('rounded-[8px] px-3 py-1.5 text-sm transition-colors', lang === l.code ? 'bg-white font-semibold text-green-800 shadow-sm' : 'text-white/85 hover:bg-white/10 hover:text-white')"
            @click="lang = l.code"
          >{{ l.label }}</button>
        </div>
      </header>

      <div class="flex flex-col gap-6">
        <!-- Environment -->
        <section class="flex flex-col gap-2 rounded-[14px] border border-neutral-300 bg-surface shadow-sm p-4">
          <span :class="labelCls">{{ t.env }}</span>
          <div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            <span class="text-neutral-600">{{ t.envApp }}</span><a :href="ENV.app" class="break-all text-green-700 hover:underline">{{ ENV.app }}</a>
            <span class="text-neutral-600">{{ t.envServer }}</span><code class="font-mono text-foreground">{{ ENV.server }}</code>
            <span class="text-neutral-600">{{ t.envKeys }}</span><a :href="ENV.keys" class="break-all text-green-700 hover:underline">{{ ENV.keys }}</a>
            <span class="text-neutral-600">{{ t.envUser }}</span><code class="font-mono text-foreground">{{ ENV.user }}</code>
          </div>
        </section>

        <!-- Base -->
        <section class="flex flex-col gap-1.5">
          <span :class="labelCls">{{ t.base }}</span>
          <code class="block break-all rounded-[10px] border border-green-200 bg-green-50 px-3.5 py-2.5 font-mono text-sm text-green-900">{{ BASE }}</code>
        </section>

        <!-- Headers -->
        <section class="flex flex-col gap-2">
          <span :class="labelCls">{{ t.headers }}</span>
          <div class="overflow-hidden rounded-[12px] border border-neutral-300 bg-surface shadow-sm">
            <table class="w-full border-collapse">
              <thead class="border-b border-neutral-300 bg-neutral-100">
                <tr><th :class="thCls">{{ t.colHeader }}</th><th :class="thCls">{{ t.colValue }}</th><th :class="thCls">{{ t.colWhen }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="h in HEADERS" :key="h.name" class="border-b border-neutral-100 last:border-0">
                  <td :class="tdCls"><code class="font-mono text-xs">{{ h.name }}</code></td>
                  <td :class="tdCls"><code class="font-mono text-xs text-neutral-600">{{ h.value }}</code></td>
                  <td :class="cn(tdCls, 'text-neutral-700')">{{ h.when[lang] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-sm leading-relaxed text-neutral-600">{{ t.keyNote }}</p>
        </section>

        <!-- Endpoints -->
        <section class="flex flex-col gap-2">
          <span :class="labelCls">{{ t.endpoints }}</span>
          <div class="overflow-hidden rounded-[12px] border border-neutral-300 bg-surface shadow-sm">
            <table class="w-full border-collapse">
              <thead class="border-b border-neutral-300 bg-neutral-100">
                <tr><th :class="thCls">{{ t.colMethod }}</th><th :class="thCls">{{ t.colPath }}</th><th :class="thCls">{{ t.colPurpose }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="e in ENDPOINTS" :key="e.path" class="border-b border-neutral-100 last:border-0">
                  <td :class="tdCls"><span :class="cn('rounded px-1.5 py-0.5 font-mono text-xs font-semibold', e.method === 'GET' ? 'bg-neutral-200 text-neutral-700' : 'bg-green-100 text-green-700')">{{ e.method }}</span></td>
                  <td :class="tdCls"><code class="font-mono text-xs">{{ e.path }}</code></td>
                  <td :class="cn(tdCls, 'text-neutral-700')">{{ e.purpose[lang] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-sm leading-relaxed text-neutral-600">{{ t.bodyNote }}</p>
        </section>

        <!-- How it works -->
        <section class="flex flex-col gap-2 rounded-[14px] border border-neutral-300 bg-surface shadow-sm p-4">
          <span :class="labelCls">{{ t.how }}</span>
          <p class="text-sm leading-relaxed text-foreground">{{ t.howP1 }}</p>
          <p class="text-sm leading-relaxed text-neutral-600">{{ t.howP2 }}</p>
        </section>

        <!-- Responses -->
        <section class="flex flex-col gap-2">
          <span :class="labelCls">{{ t.responses }}</span>
          <div class="overflow-hidden rounded-[12px] border border-neutral-300 bg-surface shadow-sm">
            <table class="w-full border-collapse">
              <thead class="border-b border-neutral-300 bg-neutral-100">
                <tr><th :class="thCls">{{ t.colCode }}</th><th :class="thCls">{{ t.colBody }}</th><th :class="thCls">{{ t.colMeaning }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in RESPONSES" :key="r.code" class="border-b border-neutral-100 last:border-0">
                  <td :class="tdCls"><span :class="cn('font-mono text-xs font-semibold tabular-nums', r.code.startsWith('2') ? 'text-positive' : 'text-negative')">{{ r.code }}</span></td>
                  <td :class="tdCls"><code class="font-mono text-xs text-neutral-600">{{ r.body }}</code></td>
                  <td :class="cn(tdCls, 'text-neutral-700')">{{ r.meaning[lang] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-sm leading-relaxed text-neutral-600">{{ t.agg }}</p>
        </section>

        <!-- Security -->
        <section class="flex flex-col gap-2 rounded-[14px] border border-neutral-300 bg-surface shadow-sm p-4">
          <span :class="labelCls">{{ t.security }}</span>
          <p class="text-sm leading-relaxed text-neutral-600">{{ t.securityP }}</p>
        </section>
      </div>
    </div>
  </div>
</template>
