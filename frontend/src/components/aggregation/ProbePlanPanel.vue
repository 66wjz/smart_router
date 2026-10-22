<template>
  <div>
    <BaseSection variant="card" title="探测排班表">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="$emit('reload')">刷新</BaseButton>
      </template>
      <ProbeScheduleTable :plan="plan" />
    </BaseSection>

    <BaseSection variant="card" title="全局探测默认值" style="margin-top: 16px">
      <BaseNotice text="未挂模板、也未自配的聚合会继承这里的值。这里仅控制「怎么探」，不控制「探哪些」。" />

      <el-form label-width="150px" style="max-width: 760px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="启用延迟探测">
              <el-switch :model-value="form.enabled"
                @update:model-value="(v: any) => patch({ enabled: Boolean(v) })" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="探测间隔（秒）">
              <el-input-number :model-value="form.interval_seconds" :min="10" style="width: 100%"
                @update:model-value="(v: any) => patch({ interval_seconds: v })" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="慢阈值（秒）">
              <el-input-number :model-value="form.slow_threshold_seconds" :min="1" style="width: 100%"
                @update:model-value="(v: any) => patch({ slow_threshold_seconds: v })" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="探测并发数">
              <el-input-number :model-value="form.max_concurrency" :min="1" :max="50" style="width: 100%"
                @update:model-value="(v: any) => patch({ max_concurrency: v })" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="不可用阈值（秒）">
              <el-input-number :model-value="form.down_threshold_seconds" :min="5" style="width: 100%"
                @update:model-value="(v: any) => patch({ down_threshold_seconds: v })" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="基准延迟（秒）">
              <el-input-number :model-value="form.base_latency" :min="0.1" :step="0.1" style="width: 100%"
                @update:model-value="(v: any) => patch({ base_latency: v })" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="探测超时（秒）">
              <el-input-number :model-value="form.timeout_seconds" :min="5" style="width: 100%"
                @update:model-value="(v: any) => patch({ timeout_seconds: v })" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="探测失败计入 Key 冷却">
              <el-switch :model-value="form.count_key_failures"
                @update:model-value="(v: any) => patch({ count_key_failures: Boolean(v) })" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="全局探测时段">
          <el-radio-group :model-value="schedule.mode"
            @update:model-value="(v: any) => patchSchedule({ mode: v === 'window' ? 'window' : 'always' })">
            <el-radio value="always">全天候</el-radio>
            <el-radio value="window">仅指定时段</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="schedule.mode === 'window'">
          <el-form-item label="星期">
            <el-checkbox-group :model-value="schedule.days"
              @update:model-value="(v: any) => patchSchedule({ days: v as number[] })">
              <el-checkbox v-for="d in DAY_OPTIONS" :key="d.value" :value="d.value">{{ d.label }}</el-checkbox>
            </el-checkbox-group>
            <BaseHint block text="不勾选 = 每天。仅作用于没有聚合/模板指定的单元。" />
          </el-form-item>
          <el-form-item label="时段窗口">
            <div class="window-list">
              <div v-for="(w, i) in schedule.windows" :key="i" class="window-row">
                <el-time-select :model-value="w.start" start="00:00" end="23:30" step="00:30" placeholder="开始"
                  style="width: 130px"
                  @update:model-value="(v: string) => patchWindow(i, { start: v })" />
                <span class="sep">→</span>
                <el-time-select :model-value="w.end" start="00:30" end="23:59" step="00:30" placeholder="结束"
                  style="width: 130px"
                  @update:model-value="(v: string) => patchWindow(i, { end: v })" />
                <BaseButton variant="danger" size="sm" @click="removeWindow(i)">删除</BaseButton>
              </div>
              <BaseButton variant="ghost" size="sm" @click="addWindow">+ 添加时段</BaseButton>
            </div>
          </el-form-item>
        </template>

        <el-form-item>
          <BaseButton variant="primary" size="sm" :disabled="saving" @click="$emit('save')">
            {{ saving ? '保存中...' : '保存全局探测设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- CH-046：与其它列表统一走 ListPage -->
    <ListPage
      title="探测单元明细"
      description="每个「上游源 × 真实模型」是一个探测单元；同一单元被多个聚合引用时只探一次"
      style="margin-top: 16px"
      :page="unitPage"
      :page-size="unitPageSize"
      :total="plan.units.length"
      @update:page="unitPage = $event"
      @update:page-size="unitPageSize = $event"
    >
      <template #toolbar>
        <ListToolbar :total="plan.units.length" dataset="probe-units" />
      </template>

      <DataTable
        :data="pagedUnits"
        :columns="unitColumns"
        row-key="key"
        empty-text="暂无探测单元"
      >
        <template #cell-upstream_name="{ row }">{{ row.upstream_name }}</template>
        <template #cell-model="{ row }"><code class="mono">{{ row.model }}</code></template>
        <template #cell-groups="{ row }">
          <BaseBadge v-for="g in row.groups" :key="g"
            :variant="row.group_kinds[g] === 'rule' ? 'purple' : 'blue'" style="margin-right: 4px">
            {{ g }}
          </BaseBadge>
          <span v-if="!row.groups.length" class="muted">仅规则/别名</span>
        </template>
        <template #cell-interval="{ row }">{{ row.interval }}s</template>
        <template #cell-latency="{ row }">{{ row.latency != null ? `${row.latency}s` : 'N/A' }}</template>
        <template #cell-last_check="{ row }">{{ fmtTime(row.last_check) }}</template>
        <template #cell-status="{ row }">
          <BaseBadge :variant="row.status === 'ok' ? 'green' : row.status === 'down' ? 'red' : 'gray'">
            {{ row.status === 'ok' ? '可用' : row.status === 'down' ? '不可用' : '未知' }}
          </BaseBadge>
          <BaseBadge v-if="!row.active_now" variant="amber" style="margin-left: 4px">时段外</BaseBadge>
          <BaseBadge v-else-if="row.stale" variant="gray" style="margin-left: 4px">数据陈旧</BaseBadge>
        </template>
      </DataTable>
    </ListPage>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import BaseSection from '@/components/base/BaseSection.vue'
import { ListPage, DataTable, ListToolbar } from '@/components/list'
import type { DataColumn } from '@/components/list'
import ProbeScheduleTable from '@/components/probe/ProbeScheduleTable.vue'
import type { ProbePlan, ProbeSchedule } from '@/api/aggregations'

const unitPage = ref(1)
const unitPageSize = ref(20)

const unitColumns: DataColumn[] = [
  { key: 'upstream_name', label: '上游源', width: 130 },
  { key: 'model', label: '真实模型名', minWidth: 200 },
  { key: 'groups', label: '引用聚合', minWidth: 200 },
  { key: 'interval', label: '间隔', width: 80 },
  { key: 'latency', label: '最近延迟', width: 90 },
  { key: 'last_check', label: '最近探测', width: 160 },
  { key: 'status', label: '状态', width: 150 },
]

const props = defineProps<{
  plan: ProbePlan
  form: Record<string, any>
  schedule: ProbeSchedule
  saving: boolean
}>()

/** 探测单元按当前页切片（CH-046：分页归列表） */
const pagedUnits = computed(() => {
  const start = (unitPage.value - 1) * unitPageSize.value
  return props.plan.units.slice(start, start + unitPageSize.value)
})

const emit = defineEmits<{
  'update:form': [value: Record<string, any>]
  'update:schedule': [value: ProbeSchedule]
  reload: []
  save: []
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

function patch(patchObj: Record<string, any>) {
  emit('update:form', { ...props.form, ...patchObj })
}

function patchSchedule(patchObj: Partial<ProbeSchedule>) {
  emit('update:schedule', { ...props.schedule, ...patchObj })
}

function patchWindow(index: number, patchObj: { start?: string; end?: string }) {
  const windows = props.schedule.windows.map((w, i) => (i === index ? { ...w, ...patchObj } : w))
  patchSchedule({ windows })
}

function addWindow() {
  patchSchedule({ windows: [...props.schedule.windows, { start: '08:00', end: '23:00' }] })
}

function removeWindow(index: number) {
  patchSchedule({ windows: props.schedule.windows.filter((_, i) => i !== index) })
}

function fmtTime(ts: number): string {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
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
.muted {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}
</style>
