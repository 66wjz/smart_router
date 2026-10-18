<template>
  <div>
    <BaseNotice :title="`${plan.summary.unit_count} 个探测单元 · 去重省 ${plan.summary.dedup_saved} 次 · 每天约 ${plan.summary.daily_requests.toLocaleString()} 次请求 · 覆盖 ${plan.summary.aggregation_count} 个聚合`" />

    <div class="sched-toolbar">
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button value="merged">合并视图</el-radio-button>
        <el-radio-button value="weekday">按星期</el-radio-button>
      </el-radio-group>
      <div class="legend">
        <span class="legend-item"><i class="cell on" /> 探测中</span>
        <span class="legend-item"><i class="cell off" /> 时段外</span>
        <span class="legend-item"><i class="cell disabled" /> 已关闭</span>
      </div>
    </div>

    <div class="sched-wrap">
      <table class="sched-table">
        <thead>
          <tr>
            <th class="col-unit">探测单元</th>
            <th v-if="viewMode === 'weekday'" class="col-day">星期</th>
            <th v-for="h in 24" :key="h" class="col-hour">{{ String(h - 1).padStart(2, '0') }}</th>
            <th class="col-interval">间隔</th>
            <th class="col-count">次/时</th>
            <th class="col-count">次/日</th>
            <th class="col-groups">引用聚合</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.key">
            <tr v-for="(dayRow, di) in row.days" :key="`${row.key}-${di}`" :class="{ 'row-alt': di > 0 }">
              <td v-if="di === 0" class="col-unit" :rowspan="row.days.length">
                <div class="unit-name">
                  <span class="unit-src">{{ row.upstream_name }}</span>
                  <code>{{ row.model }}</code>
                </div>
                <div class="unit-meta">
                  <BaseBadge :variant="row.status === 'ok' ? 'green' : row.status === 'down' ? 'red' : 'gray'">
                    {{ row.status === 'ok' ? '可用' : row.status === 'down' ? '不可用' : '未知' }}
                  </BaseBadge>
                  <span class="unit-latency">{{ row.latency != null ? `${row.latency}s` : 'N/A' }}</span>
                  <BaseBadge v-if="!row.enabled" variant="gray">探测关闭</BaseBadge>
                  <BaseBadge v-else-if="!row.active_now && viewMode === 'merged'" variant="amber">时段外</BaseBadge>
                  <BaseBadge v-else-if="row.stale" variant="gray">数据陈旧</BaseBadge>
                </div>
              </td>
              <td v-if="viewMode === 'weekday'" class="col-day">{{ DAY_LABEL[di] }}</td>
              <td v-for="(state, hi) in dayRow" :key="hi" class="col-hour">
                <i class="cell" :class="state" :title="cellTitle(row, hi, state)" />
              </td>
              <td v-if="di === 0" class="col-interval" :rowspan="row.days.length">
                {{ row.enabled ? `${row.interval}s` : '—' }}
              </td>
              <td v-if="di === 0" class="col-count" :rowspan="row.days.length">
                {{ row.enabled ? perHour(row) : 0 }}
              </td>
              <td v-if="di === 0" class="col-count" :rowspan="row.days.length">
                {{ row.enabled ? perDay(row) : 0 }}
              </td>
              <td v-if="di === 0" class="col-groups" :rowspan="row.days.length">
                <span v-for="g in row.groups" :key="g" class="group-chip"
                  :class="{ 'is-rule': row.group_kinds[g] === 'rule' }">{{ g }}</span>
                <el-text v-if="!row.groups.length" type="info" size="small">仅规则/别名</el-text>
              </td>
            </tr>
          </template>
          <tr v-if="!rows.length">
            <td :colspan="viewMode === 'weekday' ? 32 : 31" class="empty-row">当前没有探测单元</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import type { ProbePlan, ProbeSchedule, ProbeUnit } from '@/api/aggregations'

const props = defineProps<{ plan: ProbePlan }>()

const viewMode = ref<'merged' | 'weekday'>('merged')
const DAY_LABEL = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

type CellState = 'on' | 'off' | 'disabled'

interface Row extends ProbeUnit {
  enabled: boolean
  days: CellState[][]
}

const rows = computed<Row[]>(() => {
  const list = (props.plan.units || []).map((u) => {
    const enabled = u.groups.length > 0 || u.sources.includes('rule') || u.sources.includes('pointer')
    const days = Array.from({ length: viewMode.value === 'weekday' ? 7 : 1 }, (_, di) =>
      Array.from({ length: 24 }, (_, h) => cellState(u, enabled, viewMode.value === 'weekday' ? di + 1 : 0, h)),
    )
    return { ...u, enabled, days }
  })
  return list.sort((a, b) => (a.upstream + a.model).localeCompare(b.upstream + b.model))
})

/**
 * 单个小时格状态：优先看是否开启探测，再看时段
 * 时段判定用该小时的中间时刻（:30），与后端 is_active 语义一致
 */
function cellState(u: ProbeUnit, enabled: boolean, isoWeekday: number, hour: number): CellState {
  if (!enabled) return 'disabled'
  const scheds = u.schedules && u.schedules.length ? u.schedules : [u.schedule]
  // 多引用方时段取并集：任一时段允许即算探测中
  const inWindow = scheds.some((s) => scheduleCovers(s, isoWeekday, hour))
  return inWindow ? 'on' : 'off'
}

function scheduleCovers(sched: ProbeSchedule | undefined, isoWeekday: number, hour: number): boolean {
  if (!sched || sched.mode !== 'window') return true
  const days = sched.days || []
  if (isoWeekday && days.length && !days.includes(isoWeekday)) return false
  const windows = sched.windows || []
  if (!windows.length) return true
  const cur = hour * 60 + 30
  return windows.some((w) => {
    const s = toMinutes(w.start)
    const e = toMinutes(w.end)
    if (s == null || e == null || s === e) return true
    if (s < e) return cur >= s && cur < e
    return cur >= s || cur < e // 跨夜
  })
}

function toMinutes(text: string): number | null {
  const [hh, mm] = String(text || '').split(':')
  const h = Number(hh)
  const m = Number(mm ?? 0)
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null
  return h * 60 + m
}

function perHour(row: Row): number {
  return Math.max(1, Math.round(3600 / Math.max(1, row.interval)))
}

function perDay(row: Row): number {
  const hours = row.days[0].filter((s) => s === 'on').length
  return perHour(row) * hours
}

function cellTitle(row: Row, hour: number, state: CellState): string {
  const hh = String(hour).padStart(2, '0')
  if (state === 'disabled') return `${hh}:00 探测已关闭`
  return `${hh}:00 ${state === 'on' ? '探测中' : '时段外'} · 间隔 ${row.interval}s`
}
</script>

<style scoped>
.sched-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.legend {
  display: flex;
  gap: 14px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.cell {
  display: inline-block;
  width: 13px;
  height: 16px;
  border-radius: 2px;
}
.cell.on { background: var(--accent-blue, #409eff); }
.cell.off { background: var(--bg-hover, #eef0f3); }
.cell.disabled { background: repeating-linear-gradient(45deg, var(--bg-hover, #eef0f3), var(--bg-hover, #eef0f3) 3px, transparent 3px, transparent 6px); }

.sched-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}
.sched-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
  min-width: 1080px;
}
.sched-table th,
.sched-table td {
  border-bottom: 1px solid var(--border-subtle);
  padding: 6px 4px;
  text-align: center;
  white-space: nowrap;
}
.sched-table thead th {
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}
.sched-table tbody tr.row-alt {
  background: var(--bg-base);
}
.col-unit {
  text-align: left !important;
  padding-left: 10px !important;
  min-width: 210px;
  border-right: 1px solid var(--border-subtle);
}
.unit-name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.unit-src {
  color: var(--text-tertiary);
  font-size: 0.72rem;
}
.unit-name code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.76rem;
  font-weight: 600;
}
.unit-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}
.unit-latency {
  color: var(--text-tertiary);
  font-size: 0.72rem;
}
.col-hour { width: 24px; }
.col-day { width: 46px; color: var(--text-tertiary); }
.col-interval { width: 62px; }
.col-count { width: 56px; }
.col-groups {
  text-align: left !important;
  padding-left: 8px !important;
  min-width: 150px;
  white-space: normal !important;
}
.group-chip {
  display: inline-block;
  padding: 1px 6px;
  margin: 1px 3px 1px 0;
  border-radius: 999px;
  font-size: 0.7rem;
  background: var(--accent-blue-muted, rgba(64, 158, 255, 0.12));
  color: var(--accent-blue, #409eff);
}
.group-chip.is-rule {
  background: var(--accent-purple-muted, rgba(155, 89, 182, 0.14));
  color: var(--accent-purple, #9b59b6);
}
.empty-row {
  padding: 28px 0 !important;
  color: var(--text-tertiary);
}
</style>
