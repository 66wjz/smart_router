/** 探测时段的展示与校验工具（CH-026 从 Aggregated.vue 抽出） */
import type { ProbeSchedule } from '@/api/aggregations'

const DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

/** 把探测时段配置转成可读文案，如「工作日 08:00-23:00」 */
export function describeSchedule(raw: ProbeSchedule | undefined): string {
  if (!raw || raw.mode !== 'window') return '全天候'
  const days = raw.days || []
  const dayText = !days.length || days.length === 7
    ? '每天'
    : days.length === 5 && days.every((d) => d <= 5) ? '工作日'
      : days.length === 2 && days.includes(6) && days.includes(7) ? '周末'
        : days.map((d) => DAY_NAMES[d - 1]).join('、')
  const windows = raw.windows || []
  if (!windows.length) return `${dayText} 全天`
  return `${dayText} ${windows.map((w) => `${w.start}-${w.end}`).join('、')}`
}

/** 校验时段窗口，返回错误文案（空串表示通过） */
export function validateSchedule(schedule: ProbeSchedule): string {
  if (schedule.mode !== 'window') return ''
  for (const w of schedule.windows) {
    if (!w.start || !w.end) return '时段窗口需要同时填写开始和结束'
    if (w.start === w.end) return '时段的开始与结束不能相同'
  }
  return ''
}

/** 规范化：非 window 模式清空 days/windows */
export function normalizeSchedule(schedule: ProbeSchedule): ProbeSchedule {
  return {
    mode: schedule.mode,
    days: schedule.mode === 'window' ? schedule.days : [],
    windows: schedule.mode === 'window' ? schedule.windows : [],
  }
}

/** 时间戳 → HH:mm:ss */
export function fmtTime(ts: number): string {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
