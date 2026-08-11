<template>
  <div class="calendar-picker" :class="{ open: isOpen, sm: size === 'sm' }" ref="pickerRef">
    <div class="calendar-trigger" @click.stop="toggle">
      <BaseIcon name="calendar" :size="14" style="flex-shrink:0" />
      <span class="calendar-date-text">{{ displayDate || placeholder }}</span>
      <BaseIcon name="chevron-down" :size="14" style="flex-shrink:0" />
    </div>
    <div v-if="isOpen" class="calendar-panel" @click.stop>
      <div class="calendar-header">
        <button class="cal-nav-btn" @click="prevMonth">
          <BaseIcon name="chevron-left" :size="14" />
        </button>
        <span class="cal-month-title">{{ calendarTitle }}</span>
        <button class="cal-nav-btn" @click="nextMonth">
          <BaseIcon name="chevron-right" :size="14" />
        </button>
      </div>
      <div class="calendar-weekdays">
        <span v-for="w in weekdays" :key="w" class="cal-weekday">{{ w }}</span>
      </div>
      <div class="calendar-days">
        <button
          v-for="(day, idx) in calendarDays"
          :key="idx"
          class="cal-day"
          :class="{
            'other-month': !day.isCurrentMonth,
            'is-today': day.isToday,
            'is-selected': day.dateStr === selectedDate
          }"
          @click="selectDate(day.dateStr)"
        >{{ day.day }}</button>
      </div>
      <div class="calendar-footer">
        <BaseButton variant="ghost" size="sm" @click="goToday">今天</BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import dayjs from 'dayjs'
import BaseButton from '../base/BaseButton.vue'
import BaseIcon from './BaseIcon.vue'

interface CalendarDay {
  day: number
  dateStr: string
  isCurrentMonth: boolean
  isToday: boolean
}

const props = withDefaults(defineProps<{
  modelValue: string
  size?: 'default' | 'sm'
  placeholder?: string
}>(), {
  size: 'default',
  placeholder: '选择日期'
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const isOpen = ref(false)
const viewMonth = ref(dayjs().startOf('month'))
const selectedDate = ref(props.modelValue)
const pickerRef = ref<HTMLElement | null>(null)

const weekdays = ['一', '二', '三', '四', '五', '六', '日']

const calendarTitle = computed(() => {
  const d = viewMonth.value
  return `${d.year()}年${d.month() + 1}月`
})

const displayDate = computed(() => {
  if (!selectedDate.value) return ''
  const d = dayjs(selectedDate.value)
  return `${d.year()}年${d.month() + 1}月${d.date()}日`
})

const calendarDays = computed<CalendarDay[]>(() => {
  const start = viewMonth.value.startOf('month')
  // Monday-based start: shift so week starts on Monday
  const startDay = start.day() // 0=Sun, 1=Mon, ...
  const mondayOffset = startDay === 0 ? 6 : startDay - 1
  const daysInMonth = viewMonth.value.daysInMonth()
  const prevMonth = viewMonth.value.subtract(1, 'month')
  const daysInPrev = prevMonth.daysInMonth()
  const today = dayjs().format('YYYY-MM-DD')
  const result: CalendarDay[] = []

  // Previous month padding
  for (let i = mondayOffset - 1; i >= 0; i--) {
    const d = daysInPrev - i
    const m = prevMonth.month() + 1
    const y = prevMonth.year()
    result.push({
      day: d,
      dateStr: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
      isCurrentMonth: false,
      isToday: false
    })
  }

  // Current month
  for (let d = 1; d <= daysInMonth; d++) {
    const m = viewMonth.value.month() + 1
    const y = viewMonth.value.year()
    const dateStr = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    result.push({
      day: d,
      dateStr,
      isCurrentMonth: true,
      isToday: dateStr === today
    })
  }

  // Next month padding to fill 6 rows (42 cells)
  const nextMonth = viewMonth.value.add(1, 'month')
  const remaining = 42 - result.length
  for (let d = 1; d <= remaining; d++) {
    const m = nextMonth.month() + 1
    const y = nextMonth.year()
    result.push({
      day: d,
      dateStr: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
      isCurrentMonth: false,
      isToday: false
    })
  }
  return result
})

function toggle() {
  isOpen.value = !isOpen.value
  if (isOpen.value && selectedDate.value) {
    viewMonth.value = dayjs(selectedDate.value).startOf('month')
  }
}

function prevMonth() {
  viewMonth.value = viewMonth.value.subtract(1, 'month')
}

function nextMonth() {
  viewMonth.value = viewMonth.value.add(1, 'month')
}

function selectDate(dateStr: string) {
  selectedDate.value = dateStr
  emit('update:modelValue', dateStr)
  isOpen.value = false
}

function goToday() {
  const today = dayjs().format('YYYY-MM-DD')
  viewMonth.value = dayjs().startOf('month')
  selectDate(today)
}

function onClickOutside(e: MouseEvent) {
  if (isOpen.value && pickerRef.value && !pickerRef.value.contains(e.target as Node)) {
    isOpen.value = false
  }
}

watch(() => props.modelValue, (val) => {
  selectedDate.value = val
})

onMounted(() => {
  document.addEventListener('click', onClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.calendar-picker {
  position: relative;
}

.calendar-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: var(--control-height);
  background: var(--bg-base);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
  transition: border-color 0.2s;
  user-select: none;
}

.calendar-trigger:hover {
  border-color: var(--accent-blue);
}

.calendar-trigger svg {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.calendar-picker.open .calendar-trigger {
  border-color: var(--accent-blue);
}

.calendar-date-text {
  font-size: 13px;
  color: var(--text-primary);
  font-family: inherit;
  white-space: nowrap;
}

.calendar-panel {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  background: var(--bg-base);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 12px;
  z-index: var(--z-dropdown);
  min-width: 240px;
  animation: slideUp 0.15s ease;
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.cal-nav-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  transition: all 0.15s;
}

.cal-nav-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.cal-month-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.calendar-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  text-align: center;
  margin-bottom: 4px;
}

.cal-weekday {
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 4px 0;
}

.calendar-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.cal-day {
  background: none;
  border: none;
  padding: 6px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all 0.15s;
  font-family: inherit;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto;
}

.cal-day:hover {
  background: var(--bg-hover);
}

.cal-day.other-month {
  color: var(--text-tertiary);
  opacity: 0.4;
}

.cal-day.is-today {
  background: var(--accent-blue-muted);
  color: var(--accent-blue);
  font-weight: 600;
}

.cal-day.is-selected {
  background: var(--accent-blue);
  color: #fff;
  font-weight: 600;
}

.cal-day.is-selected.is-today {
  color: #fff;
}

.calendar-footer {
  margin-top: 8px;
  text-align: center;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}

/* Small size variant */
.calendar-picker.sm .calendar-trigger {
  padding: 0 8px;
  font-size: 12px;
  height: var(--control-height-sm);
  box-sizing: border-box;
}

.calendar-picker.sm .calendar-date-text {
  font-size: 12px;
}
</style>
