<template>
  <!-- CH-046：与其它列表统一走 ListPage（标题+右上操作 / 工具条 / DataTable / 分页） -->
  <ListPage
    title="探测模板"
    :page="page"
    :page-size="pageSize"
    :total="templates.length"
    @update:page="page = $event"
    @update:page-size="pageSize = $event"
  >
    <template #actions>
      <BaseButton variant="ghost" size="sm" @click="$emit('reload')">刷新</BaseButton>
      <BaseButton variant="primary" size="sm" @click="$emit('create')">+ 新建模板</BaseButton>
    </template>

    <template #notice>
      <BaseNotice
        text="模板 = 一套可复用的探测节奏（间隔 / 慢阈值 / 排序 / 时段）。多个聚合挂同一模板后共用同一节奏，改模板即全部生效；挂模板的聚合不再使用自己的探测参数。"
      />
    </template>

    <template #toolbar>
      <ListToolbar
        :count="selected.length"
        :total="templates.length"
        dataset="probe-templates"
        :actions="batchActions"
        selectable
        :all-checked="allPageChecked"
        :indeterminate="pageIndeterminate"
        batch-export
        :selected-ids="selected.map(String)"
        @toggle-all="toggleAllOnPage"
        @clear="clearSelection"
      />
    </template>

    <DataTable
      ref="tableRef"
      :data="paged"
      :columns="columns"
      row-key="id"
      selectable
      empty-text="还没有探测模板。可以先建一个「标准-全天」模板，再挂到常用聚合上。"
      @selection-change="(rows: any[]) => (selected = rows.map((r) => r.id))"
    >
      <template #cell-name="{ row }">
        <span class="tpl-name">{{ row.name }}</span>
        <span v-if="row.remark" class="tpl-remark"> {{ row.remark }}</span>
      </template>
      <template #cell-interval_seconds="{ row }">{{ row.interval_seconds }}s</template>
      <template #cell-slow_threshold_seconds="{ row }">
        {{ row.slow_threshold_seconds != null ? `${row.slow_threshold_seconds}s` : '跟随全局' }}
      </template>
      <template #cell-sort_mode="{ row }">
        <BaseBadge :variant="row.sort_mode === 'latency' ? 'amber' : 'gray'">
          {{ row.sort_mode === 'latency' ? '速度优先' : '稳定优先' }}
        </BaseBadge>
      </template>
      <template #cell-schedule="{ row }">{{ describeSchedule(row.schedule) }}</template>
      <template #cell-refs="{ row }">
        <BaseBadge v-for="n in row.ref_names || []" :key="n" variant="blue" style="margin-right: 4px">{{ n }}</BaseBadge>
        <span v-if="!row.ref_count" class="muted">暂无聚合使用</span>
      </template>
      <template #cell-actions="{ row }">
        <RowActions
          :items="[
            { label: '编辑', onClick: () => $emit('edit', row) },
            { label: '删除', variant: 'danger', onClick: () => $emit('remove', row) },
          ]"
        />
      </template>
    </DataTable>
  </ListPage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import { ListPage, DataTable, ListToolbar, RowActions } from '@/components/list'
import type { DataColumn } from '@/components/list'
import { describeSchedule } from './schedule'
import type { ProbeTemplate } from '@/api/aggregations'

const props = defineProps<{
  templates: ProbeTemplate[]
}>()

const emit = defineEmits<{
  reload: []
  create: []
  edit: [row: ProbeTemplate]
  remove: [row: ProbeTemplate]
}>()

const page = ref(1)
const pageSize = ref(20)
const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return props.templates.slice(start, start + pageSize.value)
})

// ---------- 多选 + 批量删除（CH-047） ----------
const tableRef = ref<any>(null)
const selected = ref<number[]>([])

const pageIds = computed(() => paged.value.map((r) => r.id))
const allPageChecked = computed(() =>
  pageIds.value.length > 0 && pageIds.value.every((id) => selected.value.includes(id)),
)
const pageIndeterminate = computed(() => {
  const hit = pageIds.value.filter((id) => selected.value.includes(id)).length
  return hit > 0 && hit < pageIds.value.length
})

function toggleAllOnPage(checked: boolean) {
  if (checked) {
    selected.value = [...new Set([...selected.value, ...pageIds.value])]
  } else {
    const drop = new Set(pageIds.value)
    selected.value = selected.value.filter((id) => !drop.has(id))
  }
  tableRef.value?.setSelection?.(selected.value.map(String))
}

function clearSelection() {
  selected.value = []
  tableRef.value?.clearSelection?.()
}

/**
 * 批量删除（CH-047）：逐个交给父组件走它原有的确认 + 联动清理逻辑，
 * 避免在面板里另写一套删除（模板被聚合引用时要提示并回退参数）。
 * 父组件的 remove 是异步的，这里用 Promise.all 串起来后清空选中。
 */
async function batchDelete() {
  const rows = props.templates.filter((t) => selected.value.includes(t.id))
  if (!rows.length) return
  if (!await confirmDanger(`确定删除选中的 ${rows.length} 个探测模板吗？`, '请逐个确认；被聚合引用的模板删除后，聚合会回退到自配参数。')) return

  for (const row of rows) {
    emit('remove', row)
  }
  // 父组件逐个处理后刷新列表，这里直接清空选中，等新数据回来
  selected.value = []
  tableRef.value?.clearSelection?.()
}

const batchActions = computed(() => [
  { label: '批量删除', variant: 'danger' as const, onClick: () => batchDelete() },
])

const columns: DataColumn[] = [
  { key: 'name', label: '模板名', minWidth: 200 },
  { key: 'interval_seconds', label: '间隔', width: 90 },
  { key: 'slow_threshold_seconds', label: '慢阈值', width: 100 },
  { key: 'sort_mode', label: '排序', width: 100 },
  { key: 'schedule', label: '探测时段', minWidth: 180 },
  { key: 'refs', label: '被引用', minWidth: 200 },
  { key: 'actions', label: '操作', width: 140, align: 'center' },
]
</script>

<style scoped>
.tpl-name {
  font-weight: 600;
}
.tpl-remark {
  color: var(--text-tertiary);
  margin-left: 8px;
  font-size: 0.78rem;
}
.muted {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}
</style>
