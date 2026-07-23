<script setup lang="ts">
import { ref, computed } from 'vue'
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

// Lightweight date picker (no native browser calendar). modelValue is 'YYYY-MM-DD'.
const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

function parse(s: string): Date {
  const [y, m, d] = (s || '').split('-').map(Number)
  if (!y) return new Date()
  return new Date(y, (m || 1) - 1, d || 1)
}
function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

const open = ref(false)
const selected = computed(() => parse(props.modelValue))
const viewYear = ref(selected.value.getFullYear())
const viewMonth = ref(selected.value.getMonth())
const today = new Date()

const label = computed(() =>
  selected.value.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }),
)

const grid = computed(() => {
  const first = new Date(viewYear.value, viewMonth.value, 1)
  const startDow = (first.getDay() + 6) % 7 // Monday = 0
  const daysInMonth = new Date(viewYear.value, viewMonth.value + 1, 0).getDate()
  const cells: Array<{ date: Date; inMonth: boolean }> = []
  for (let i = 0; i < startDow; i++) {
    cells.push({ date: new Date(viewYear.value, viewMonth.value, 1 - (startDow - i)), inMonth: false })
  }
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push({ date: new Date(viewYear.value, viewMonth.value, day), inMonth: true })
  }
  while (cells.length % 7 !== 0) {
    const last = cells[cells.length - 1].date
    cells.push({ date: new Date(last.getFullYear(), last.getMonth(), last.getDate() + 1), inMonth: false })
  }
  return cells
})

function toggle(): void {
  if (!open.value) {
    viewYear.value = selected.value.getFullYear()
    viewMonth.value = selected.value.getMonth()
  }
  open.value = !open.value
}
function prevMonth(): void {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value -= 1 } else { viewMonth.value -= 1 }
}
function nextMonth(): void {
  if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value += 1 } else { viewMonth.value += 1 }
}
function pick(d: Date): void {
  emit('update:modelValue', toISO(d))
  open.value = false
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="flex h-11 w-full items-center justify-between rounded-[10px] border border-neutral-200 bg-surface px-3 text-left text-sm text-foreground outline-none transition-colors focus:border-green-500"
      @click="toggle"
    >
      <span>{{ label }}</span>
      <Calendar class="size-4 shrink-0 text-neutral-400" />
    </button>

    <div v-if="open" class="mt-2 rounded-[12px] border border-neutral-200 bg-surface p-3 shadow-sm">
      <div class="mb-2 flex items-center justify-between">
        <button type="button" class="flex size-8 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-neutral-100" @click="prevMonth">
          <ChevronLeft class="size-4" />
        </button>
        <span class="text-sm font-medium text-foreground">{{ MONTHS[viewMonth] }} {{ viewYear }}</span>
        <button type="button" class="flex size-8 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-neutral-100" @click="nextMonth">
          <ChevronRight class="size-4" />
        </button>
      </div>
      <div class="grid grid-cols-7 gap-0.5">
        <span v-for="w in WEEKDAYS" :key="w" class="flex h-8 items-center justify-center text-xs text-neutral-400">{{ w }}</span>
        <button
          v-for="(c, i) in grid"
          :key="i"
          type="button"
          :class="cn(
            'flex h-9 items-center justify-center rounded-lg text-sm tabular-nums transition-colors',
            c.inMonth ? 'text-foreground hover:bg-neutral-100' : 'text-neutral-300',
            sameDay(c.date, selected) && 'bg-primary font-medium text-white hover:bg-primary',
            !sameDay(c.date, selected) && sameDay(c.date, today) && 'ring-1 ring-inset ring-primary/40',
          )"
          @click="pick(c.date)"
        >{{ c.date.getDate() }}</button>
      </div>
    </div>
  </div>
</template>
