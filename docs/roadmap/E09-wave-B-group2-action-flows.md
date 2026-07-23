# E09 Wave B — Group 2: Action Flows (B-9 + B-12 + B-13)

**Batch:** три связанных slice-а с общим паттерном «menu/CTA → sheet/dialog → backend action».
**Цель:** замкнуть остаточные UI потоки — история+attachments (B-9), амендменты (B-12), отмена/реверс (B-13).

> Sonnet делает batch как **три последовательных коммита**, не один. Каждый коммит = один slice. STOP-points обрабатываются стандартно.

---

## Architectural baseline (общее для всех трёх)

- Размер любого нового `.vue` — стандартное ≤300 строк правило
- `ProcurementWorkspaceView.vue` — **бюджет расширен до 320 строк** (orchestrator, оправдано для 7 карточек + 5+ sheets)
- Если View > 320 после интеграции — STOP, выделить orchestration в composable

---

# B-9 — История и документы (attachments)

**Файлы:**
- `ProcurementCardHistory.vue` ≤220 (events timeline + attachments)
- `AttachmentList.vue` ≤120 (read+delete grid)
- `AttachmentUploader.vue` ≤120 (file input + upload progress)

**Pre-flight reads:**
1. `frontend/src/api/attachments.ts` — должна быть готова (Wave A S-4). Если файла нет → STOP.
2. `procurement.documents` в payload — найти `events[]` или `history[]` shape.
3. `frontend/src/api/partnerships.ts:1083-1100` — посмотреть как существующие методы делают multipart upload, скопировать pattern.

**Контракт:**

`AttachmentList.vue`:
```ts
defineProps<{ attachments: Attachment[]; canDelete: boolean }>()
defineEmits<{ view: [id: number]; delete: [id: number] }>()
```
Grid с file icon + name + uploaded_by + date. Click → view (open in new tab). Trash → confirm + delete.

`AttachmentUploader.vue`:
```ts
defineProps<{
  attachableType: 'procurement' | 'receive_batch'
  attachableId: number
  defaultKind: 'INVOICE' | 'RECEIPT_PHOTO' | 'DOCUMENT' | 'OTHER'
}>()
defineEmits<{ uploaded: [attachment: Attachment] }>()
```
File input, optional caption, kind selector. На submit — `uploadAttachment()` from api/attachments.ts.

`ProcurementCardHistory.vue`:
- Header: «История и документы» + counts.
- Свёрнута по умолчанию (collapsible через v-if).
- Section 1: Attachments via AttachmentList (procurement-level).
- Section 2: AttachmentUploader (если editable).
- Section 3: Events timeline — простой список из `procurement.documents.history` или events array. По 10 последних, кнопка «показать все».

**View integration:** одна импорт + одна строка в cards-container. ≤10 строк view-кода.

**STOP-points:**
1. api/attachments.ts отсутствует — Wave A S-4 не пробросил.
2. multipart upload patterns в проекте нет — STOP, спрашиваем.
3. View > 320 строк после интеграции.

**Commit:** `feat(E09-wave-B-9): history card + attachments uploader/list`

---

# B-12 — Amendment flow

**Файлы:**
- `AmendmentSheet.vue` ≤280 (sheet с before/after preview + reason input)

**Pre-flight reads:**
1. Wave A S-7 endpoints — какие именно actions есть в `WorkspaceActionKey` для амендментов. Скорее всего что-то вроде `AMEND_ITEMS`, `AMEND_EXPENSES`. Проверить.
2. `Procurement.documents.amendments[]` shape если есть в payload (для отображения истории амендментов).

**Контекст:** в B-2 header action menu имеет item «Изменить состав» (key=`amend`). Сейчас это toast placeholder. B-12 заменяет toast реальным sheet.

**Контракт:**

`AmendmentSheet.vue`:
```ts
defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  target: 'items' | 'expenses'  // что амендим
}>()
defineEmits<{
  'update:open': [value: boolean]
  saved: []  // parent перезагружает payload
}>()
```

UX:
1. Sheet открывается с target selector в header (items/expenses chips).
2. Body: пере-использует `ProcurementItemEditSheet` / `ProcurementExpenseEditSheet` UI patterns inline (не nested sheet — copy structure).
3. Внизу обязательное **reason textarea** (амендмент требует обоснование).
4. На save → dispatch соответствующий AMEND_* action.
5. Backend сам создаёт `ProcurementAmendment` запись (Wave A S-7).

**Альтернатива (если sheet > 280 строк):** запускать стандартный `ProcurementItemEditSheet` с дополнительным prop `mode: 'amend'` который требует reason. STOP и обсуждаем если sheet пухнет.

**View integration:**
- Header `menu-action` event с key=`amend` → открывает AmendmentSheet
- ~15 строк дополнительного кода (state + handler + render)

**STOP-points:**
1. AMEND_ITEMS / AMEND_EXPENSES не существуют в WorkspaceActionKey — Wave A S-7 не пробросил.
2. Amendment payload требует особой структуры — выяснить.
3. Sheet > 280 строк — обсуждаем decomposition.

**Commit:** `feat(E09-wave-B-12): amendment flow for items/expenses`

---

# B-13 — Cancel + Reverse receive flows

**Файлы:**
- `ProcurementCancelDialog.vue` ≤120 (confirmation dialog + reason)
- `ReverseReceiveBatchDialog.vue` ≤140 (confirmation + warning о connectedness)

**Pre-flight reads:**
1. Action keys в `WorkspaceActionKey` — найти `CANCEL_WORKSPACE` (видели в B-1 pre-flight) и `REVERSE_RECEIVE_BATCH` (Wave A S-6). Если отсутствуют → STOP.
2. Backend strict reject если Lot has sales — UI **должен это объяснить** при отказе.

**Контекст:** B-2 header action menu имеет items «Отменить приход» (key=`cancel`) и «Отменить приёмку» (key=`reverse_receive`). Оба — placeholder toast. B-13 заменяет реальными dialogs.

**Контракт:**

`ProcurementCancelDialog.vue`:
- Стандартный modal dialog (не bottom sheet — destructive action нужен явный modal).
- Header: «Отменить приход #N?»
- Body: warning text + reason textarea.
- Backend правило: запрещён если payments или receive batches — UI **превентивно скрывает** action в menu если эти условия выполнены. Используй `procurement.policy.allowed_actions` если backend exposes flag. Иначе client-side check: `payments.length === 0 && receive_batches.length === 0`.
- Кнопки: Cancel / Confirm (destructive red).

`ReverseReceiveBatchDialog.vue`:
- Modal dialog.
- Header: «Отменить приёмку #N?»
- Body: показать какие Lots и какие quantities будут реверсированы. Warning если Lot уже имеет sales — kde **disabled confirm + сообщение** «Один из лотов уже продан, реверсал недоступен. Используйте отдельную корректировку склада (в разработке).»
- Reason textarea.
- Confirm → dispatch REVERSE_RECEIVE_BATCH с batch_id + reason.

**View integration:**
- Header `menu-action` event с key=`cancel` → если allowed — открывает CancelDialog
- Header `menu-action` event с key=`reverse_receive` → если есть batches — открывает selector batches → ReverseDialog
- Action menu items в header должны **conditionally hide** по procurement state (передаём через props в Header)

**STOP-points:**
1. `CANCEL_WORKSPACE` или `REVERSE_RECEIVE_BATCH` actions отсутствуют.
2. Header не поддерживает conditional hiding menu items — мелкий refactor B-2 component.

**Commit:** `feat(E09-wave-B-13): cancel procurement + reverse receive batch dialogs`

---

## После Group 2 (B-9, B-12, B-13)

View должен быть ≤320 строк, в идеале ≤300. Если ≥320 — выделим
orchestration в `useProcurementWorkspaceActions` composable.

Дальше Группа 3 (Group 3):
- B-10 (AT_RECEIPT combined receive+pay) — solo
- B-11 (Conditional matrix orchestration + readiness indicators) — solo

Group 4: B-14 (polish) solo.

## Промпты для Sonnet (по одному)

После каждого commit прислать результат, я ревью, дам следующий промпт.

**B-9:**
```
Read /Users/aziztohirov/Desktop/Projects/microposs/docs/roadmap/E09-wave-B-group2-action-flows.md
section B-9 and execute it. View budget extended to ≤320 in this group.
Three STOP-points listed.
```

**B-12 (после B-9):**
```
Continue Group 2 from the same plan: section B-12 (Amendment flow).
B-9 already committed. Three STOP-points.
```

**B-13 (после B-12):**
```
Continue Group 2 from the same plan: section B-13 (Cancel + Reverse
receive dialogs). B-9 and B-12 committed. Two STOP-points.
```
