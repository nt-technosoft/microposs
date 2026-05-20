# E09 Wave B — Slice B-1 Execution Plan (для Sonnet)

**Slice:** B-1 — Shell + routing + store + empty workspace
**Цель:** заменить старый `ProcurementWorkspace.vue` (405 строк) на новый
`ProcurementWorkspaceView.vue` shell с правильной структурой (sticky
header / scroll body / sticky bottom action bar) и Pinia store. Body
пустой — карточки добавляются в последующих slice-ах.

> Опус согласовал архитектурные решения. Sonnet исполняет.
> Любой branch point вне этого плана → STOP, surface founder'у.
>
> Связанные документы:
> - [`E09-wave-B-ui-design-detailed.md`](./E09-wave-B-ui-design-detailed.md) — полный дизайн (mockups, contracts)
> - [`E09-procurement-ui-design.md`](./E09-procurement-ui-design.md) — mental model
> - [`E09-procurement-completeness.md`](./E09-procurement-completeness.md) — эпик

---

## Pre-flight reads

Перед Slice 1 прочитать:
1. `frontend/src/modules/intake/views/ProcurementWorkspace.vue` — текущий
   главный экран. Понять структуру **поверхностно**, не копировать.
   Назначение — увидеть какие external dependencies используются (stores,
   API clients) и не пропустить их в новой реализации.
2. `frontend/src/router/routes.ts` lines 115-150 — текущие routes для
   procurements.
3. `frontend/src/api/partnerships.ts` — функции `fetchProcurementWorkspace`,
   `createProcurementWorkspace`, `dispatchWorkspaceAction` (или их аналоги).

Если каких-то из этих API функций не существует с такими именами — STOP,
surface, потому что план их подразумевает.

---

## Контракт

### Новые файлы

**1. `frontend/src/modules/intake/stores/procurementWorkspace.ts`** (Pinia store)

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchProcurementWorkspace,
  createProcurementWorkspace,
  dispatchWorkspaceAction,
} from '@/api/partnerships'
// Адаптируй имена если они в проекте другие — STOP если не нашёл

export interface ProcurementWorkspacePayload {
  // shape из существующего API; не пересоздавай — используй существующий тип
}

export const useProcurementWorkspaceStore = defineStore('procurementWorkspace', () => {
  const procurement = ref<ProcurementWorkspacePayload | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  let abortController: AbortController | null = null

  function $reset(): void {
    abortController?.abort()
    abortController = null
    procurement.value = null
    isLoading.value = false
    error.value = null
  }

  async function load(procurementId: number): Promise<void> {
    abortController?.abort()
    abortController = new AbortController()
    isLoading.value = true
    error.value = null
    try {
      procurement.value = await fetchProcurementWorkspace(procurementId, {
        signal: abortController.signal,
      })
    } catch (err) {
      if ((err as any)?.name === 'AbortError') return
      error.value = String((err as any)?.message ?? err)
    } finally {
      isLoading.value = false
    }
  }

  async function createDraft(payload: {
    funding_source?: string
    primary_currency?: string
    supplier_id?: number | null
    agreement_id?: number | null
  }): Promise<number> {
    const created = await createProcurementWorkspace(payload)
    procurement.value = created
    return created.id
  }

  async function dispatch(action: string, payload: Record<string, unknown>): Promise<void> {
    if (!procurement.value) throw new Error('No procurement loaded')
    procurement.value = await dispatchWorkspaceAction(
      procurement.value.id,
      action,
      payload,
    )
  }

  // ───── Computed view-models — будут наращиваться в следующих slice-ах
  const status = computed(() => procurement.value?.status ?? null)

  return {
    procurement,
    isLoading,
    error,
    status,
    $reset,
    load,
    createDraft,
    dispatch,
  }
})
```

**2. `frontend/src/modules/intake/views/ProcurementWorkspaceView.vue`** (new shell)

Минимальная структура — заполняется в B-2 (header + bottom bar) и далее.

```vue
<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProcurementWorkspaceStore } from '@/modules/intake/stores/procurementWorkspace'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useProcurementWorkspaceStore()
const { procurement, isLoading, error } = storeToRefs(store)

async function ensureWorkspace(): Promise<void> {
  const id = route.params.id ? Number(route.params.id) : null
  if (id) {
    await store.load(id)
  } else {
    // route /procurements/create — создаём новый draft
    const draftId = await store.createDraft({})
    await router.replace({ name: 'procurement-detail', params: { id: draftId } })
  }
}

onMounted(ensureWorkspace)
watch(() => route.params.id, ensureWorkspace)
onBeforeUnmount(() => store.$reset())
</script>

<template>
  <div class="workspace">
    <!-- Header сюда в B-2 -->
    <header class="workspace-header-placeholder">
      <button class="back-btn" @click="router.back()" aria-label="Назад">←</button>
      <h1>{{ procurement ? `Приход #${procurement.id}` : 'Новый приход' }}</h1>
    </header>

    <main class="workspace-body">
      <div v-if="isLoading" class="state state-loading">Загрузка…</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>
      <div v-else-if="!procurement" class="state state-empty">Нет данных</div>
      <div v-else class="cards-container">
        <!-- Карточки добавляются в B-3 .. B-9 -->
        <div class="card-placeholder">Карточки появятся в следующих slice-ах</div>
      </div>
    </main>

    <!-- Bottom action bar сюда в B-2 -->
    <footer class="workspace-action-bar-placeholder">
      <button class="action-btn" disabled>Сохранить черновик</button>
    </footer>
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100dvh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  background: var(--color-bg-secondary);
}

.workspace-header-placeholder {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-secondary) 92%, transparent);
  backdrop-filter: blur(14px);
}

.workspace-header-placeholder h1 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  text-align: center;
}

.back-btn {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 24px;
}

.workspace-body {
  overflow-y: auto;
  padding: var(--space-4);
  padding-bottom: var(--space-8);
}

.cards-container {
  display: grid;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
}

.card-placeholder {
  padding: var(--space-4);
  background: var(--color-bg-primary);
  border: 1px dashed var(--color-border-subtle);
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  text-align: center;
}

.state {
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--color-text-secondary);
}

.state-error {
  color: var(--color-danger);
}

.workspace-action-bar-placeholder {
  position: sticky;
  bottom: 0;
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-subtle);
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.04);
}

.action-btn {
  flex: 1;
  min-height: 48px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--color-brand-600);
  color: white;
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
}

.action-btn:disabled {
  opacity: 0.55;
}
</style>
```

### Изменённые файлы

**`frontend/src/router/routes.ts`** — переключить три procurement-route-а на новый view:

```typescript
{
  path: '/procurements/create',
  name: 'procurement-create',
  component: () => import('@/modules/intake/views/ProcurementWorkspaceView.vue'),  // CHANGED
  meta: { roles: ['owner', 'warehouse'] },
},
{
  path: '/procurements/:id/edit',
  name: 'procurement-edit',
  component: () => import('@/modules/intake/views/ProcurementWorkspaceView.vue'),  // CHANGED
  meta: { roles: ['owner', 'warehouse'] },
},
{
  path: '/procurements/:id',
  name: 'procurement-detail',
  component: () => import('@/modules/intake/views/ProcurementWorkspaceView.vue'),  // CHANGED
  meta: { roles: ['owner', 'warehouse'] },
},
```

### Переименование старого файла (НЕ удаление)

`frontend/src/modules/intake/views/ProcurementWorkspace.vue` → `frontend/src/modules/intake/views/ProcurementWorkspace.legacy.vue`

Это **критически важно** — founder указал что старый код используется как reference для будущих slice-ов. Не удалять.

После переименования — никакой импорт его не должен использовать. Проверь grep:
```bash
grep -rn "ProcurementWorkspace" frontend/src --include="*.vue" --include="*.ts" | grep -v "legacy"
```

Все ссылки кроме routes (которые мы уже переключили на View) и самого `.legacy.vue` файла — должны быть на новый ProcurementWorkspaceView. Если нашёл что-то ещё — STOP, surface.

---

## Что НЕ делаем в этом slice

- НЕ удаляем существующие components в `components/workspace/` — они будут переиспользованы в B-3..B-9 (variant picker, quick product sheet, agreement forms, etc.)
- НЕ строим header полностью — это B-2.
- НЕ строим bottom action bar полностью — это B-2.
- НЕ добавляем карточки — это B-3..B-9.
- НЕ удаляем `ProcurementWorkspace.legacy.vue` — это reference на весь Wave B.
- НЕ трогаем backend.

---

## Проверка

После slice — посетить три URL:
1. `/procurements/create` — должен открыться пустой shell, создаться draft, redirect на `/procurements/:id`
2. `/procurements/:existing_id` — должен open shell с loaded procurement
3. `/procurements/:non_existing_id` — должен показать error state

В каждом случае:
- Header показывает корректный title
- Body показывает placeholder
- Bottom bar показывает disabled action

**Запуск dev server** (если возможно в окружении Sonnet):
```bash
cd /Users/aziztohirov/Desktop/Projects/microposs/frontend
npm run dev
```

Если dev server недоступен в окружении Sonnet — surface, founder проверит вручную.

---

## STOP-точки (когда Sonnet прекращает работу и surface)

1. **API функции не найдены** — если `fetchProcurementWorkspace` /
   `createProcurementWorkspace` / `dispatchWorkspaceAction` отсутствуют в
   `api/partnerships.ts` с такими именами. Не угадывать имена.
2. **CSS переменные не найдены** — если `--color-bg-secondary`,
   `--space-4`, `--text-lg`, `--radius-lg` и подобные отсутствуют в
   design tokens проекта. Surface для уточнения какие токены доступны.
3. **Routing не работает** — если три route-а не переключаются на новый
   view (404 или 500). Surface.
4. **TypeScript ошибки** — если новый store или view не компилируется
   из-за несовместимых типов с существующим api/partnerships.ts.
   Surface, не приукрашивать `any`.
5. **Существующая зависимость от ProcurementWorkspace.vue** — если grep
   находит импорт старого файла кроме routes и самого `.legacy.vue`.
   Surface.

---

## Commit

После всех изменений и проверок:

```
feat(E09-wave-B-1): procurement workspace shell + Pinia store + routing

Replaces the legacy ProcurementWorkspace.vue (405 lines) with a clean
shell at ProcurementWorkspaceView.vue that follows the new design
anchor — sticky header, scroll body, sticky bottom action bar. The
body is intentionally empty (placeholder); cards are added in slices
B-3 through B-9.

A new Pinia store at modules/intake/stores/procurementWorkspace.ts
holds the loaded procurement, exposes load() / createDraft() /
dispatch() and follows the project's AbortController-on-load
convention (CLAUDE.md frontend rules).

Routes for /procurements/create, /procurements/:id, and
/procurements/:id/edit are repointed at the new view. Three legacy
intake redirects below them remain unchanged.

The legacy view is renamed to ProcurementWorkspace.legacy.vue —
preserved as reference material for the upcoming B-3..B-9 slices
where individual cards are rebuilt.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## После Slice B-1

Sonnet возвращает founder'у:
- Список commits
- Список STOP-точек если встретились
- Если slice прошёл без stop — готовность к Slice B-2 (header + bottom action bar)

Founder ревью + опус ревью + go/no-go для B-2.
