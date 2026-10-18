<template>
  <el-form :model="form" label-width="130px">
    <el-form-item v-if="mode === 'aggregation'" label="使用探测模板">
      <el-select
        :model-value="form.template_id ?? 0"
        style="width: 260px"
        @update:model-value="(v: any) => patch({ template_id: Number(v) || null })"
      >
        <el-option :value="0" label="不使用（按本聚合自配）" />
        <el-option v-for="t in templates" :key="t.id" :value="t.id"
          :label="`${t.name} · ${t.interval_seconds}s`" />
      </el-select>
      <el-text v-if="form.template_id" type="info" size="small" style="margin-left: 10px">
        节奏与时段由模板决定，下方自配项不生效
      </el-text>
    </el-form-item>

    <el-form-item v-if="mode === 'aggregation'" label="启用定时探测">
      <el-switch :model-value="form.enabled" @update:model-value="(v: any) => patch({ enabled: Boolean(v) })" />
      <BaseHint inline :text="form.enabled ? '按生效节奏探测，结果用于候选排序' : '关闭后本聚合不新增探测单元（仍可能被其他聚合复用）'" />
    </el-form-item>

    <div :class="{ 'is-locked': Boolean(form.template_id) }">
      <el-form-item label="探测间隔（秒）">
        <el-input-number
          :model-value="form.interval_seconds ?? 0"
          :min="0" :step="10" :disabled="Boolean(form.template_id)" style="width: 200px"
          @update:model-value="(v: any) => patch({ interval_seconds: Number(v) || null })"
        />
        <BaseHint inline :text="form.template_id ? '由模板决定' : `0 = 跟随全局 ${globalInterval}s；多聚合共用同一单元时取最小值`" />
      </el-form-item>

      <el-form-item label="慢阈值（秒）">
        <el-input-number
          :model-value="form.slow_threshold_seconds ?? 0"
          :min="0" :step="1" :disabled="Boolean(form.template_id)" style="width: 200px"
          @update:model-value="(v: any) => patch({ slow_threshold_seconds: Number(v) || null })"
        />
        <BaseHint inline :text="form.template_id ? '由模板决定' : '0 = 跟随全局；超过此延迟的成员排到后面'" />
      </el-form-item>

      <el-form-item label="排序模式">
        <el-radio-group :model-value="form.sort_mode" :disabled="Boolean(form.template_id)"
          @update:model-value="(v: any) => patch({ sort_mode: v })">
          <el-radio value="stable">稳定优先（保持我的顺序，慢的沉底）</el-radio>
          <el-radio value="latency">速度优先（按实时延迟排序）</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-divider content-position="left">探测时段</el-divider>

      <el-form-item label="时段模式">
        <el-radio-group :model-value="form.schedule.mode" :disabled="Boolean(form.template_id)"
          @update:model-value="(v: any) => patchSchedule({ mode: v })">
          <el-radio value="always">全天候</el-radio>
          <el-radio value="window">仅指定时段</el-radio>
        </el-radio-group>
      </el-form-item>

      <template v-if="form.schedule.mode === 'window'">
        <el-form-item label="星期">
          <el-checkbox-group :model-value="form.schedule.days" :disabled="Boolean(form.template_id)"
            @update:model-value="(v: any) => patchSchedule({ days: v })">
            <el-checkbox v-for="d in DAY_OPTIONS" :key="d.value" :value="d.value">{{ d.label }}</el-checkbox>
          </el-checkbox-group>
          <BaseHint text="不勾选 = 每天都探测" />
        </el-form-item>

        <el-form-item label="时段窗口">
          <div class="window-list">
            <div v-for="(w, i) in form.schedule.windows" :key="i" class="window-row">
              <el-time-select :model-value="w.start" start="00:00" end="23:30" step="00:30"
                placeholder="开始" style="width: 130px" :disabled="Boolean(form.template_id)"
                @update:model-value="(v: any) => updateWindow(i, 'start', v)" />
              <span class="sep">→</span>
              <el-time-select :model-value="w.end" start="00:30" end="23:59" step="00:30"
                placeholder="结束" style="width: 130px" :disabled="Boolean(form.template_id)"
                @update:model-value="(v: any) => updateWindow(i, 'end', v)" />
              <BaseButton variant="danger" size="sm" :disabled="Boolean(form.template_id)"
                @click="removeWindow(i)">删除</BaseButton>
            </div>
            <BaseButton variant="ghost" size="sm" :disabled="Boolean(form.template_id)" @click="addWindow">
              + 添加时段
            </BaseButton>
            <BaseHint text="例：08:00→23:00 表示夜间不探测；23:00→07:00 表示只在这个跨夜时段探测。时段外保留最后一次结果并标记「时段外」。" />
          </div>
        </el-form-item>

        <el-form-item label="快捷模板">
          <BaseButton variant="ghost" size="sm" :disabled="Boolean(form.template_id)"
            @click="applyPreset('workday')">工作日全天</BaseButton>
          <BaseButton variant="ghost" size="sm" :disabled="Boolean(form.template_id)"
            @click="applyPreset('daytime')">每天 08:00-23:00</BaseButton>
          <BaseButton variant="ghost" size="sm" :disabled="Boolean(form.template_id)"
            @click="applyPreset('weekend')">仅周末</BaseButton>
        </el-form-item>
      </template>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import BaseButton from '@/components/base/BaseButton.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import type { ProbeSchedule, ProbeTemplate } from '@/api/aggregations'

export interface ProbeFormModel {
  enabled: boolean
  template_id: number | null
  interval_seconds: number | null
  slow_threshold_seconds: number | null
  sort_mode: 'stable' | 'latency'
  schedule: ProbeSchedule
}

const props = withDefaults(defineProps<{
  form: ProbeFormModel
  templates?: ProbeTemplate[]
  globalInterval?: number
  /** aggregation = 聚合配置（可选模板、可开关探测）；template = 模板编辑（只有节奏与时段） */
  mode?: 'aggregation' | 'template'
}>(), {
  templates: () => [],
  globalInterval: 120,
  mode: 'aggregation',
})

const emit = defineEmits<{
  'update:form': [value: ProbeFormModel]
}>()

const DAY_OPTIONS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
]

function patch(part: Partial<ProbeFormModel>) {
  emit('update:form', { ...props.form, ...part })
}

function patchSchedule(part: Partial<ProbeSchedule>) {
  patch({ schedule: { ...props.form.schedule, ...part } as ProbeSchedule })
}

function updateWindow(index: number, key: 'start' | 'end', value: string) {
  const windows = props.form.schedule.windows.map((w, i) =>
    i === index ? { ...w, [key]: value } : { ...w },
  )
  patchSchedule({ windows })
}

function addWindow() {
  patchSchedule({ windows: [...props.form.schedule.windows, { start: '08:00', end: '23:00' }] })
}

function removeWindow(index: number) {
  patchSchedule({ windows: props.form.schedule.windows.filter((_, i) => i !== index) })
}

function applyPreset(kind: string) {
  if (kind === 'workday') {
    patchSchedule({ mode: 'window', days: [1, 2, 3, 4, 5], windows: [] })
  } else if (kind === 'daytime') {
    patchSchedule({ mode: 'window', days: [], windows: [{ start: '08:00', end: '23:00' }] })
  } else if (kind === 'weekend') {
    patchSchedule({ mode: 'window', days: [6, 7], windows: [] })
  }
}
</script>

<style scoped>
.window-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.window-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.window-row .sep {
  color: var(--text-tertiary);
}
.is-locked {
  opacity: 0.6;
}
</style>
