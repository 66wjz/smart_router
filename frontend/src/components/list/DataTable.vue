<template>
  <div class="data-table">
    <el-table
      ref="tableRef"
      :data="data"
      :size="density === 'compact' ? 'small' : 'default'"
      :row-key="rowKey"
      stripe
      :border="false"
      :highlight-current-row="clickableRow"
      :row-class-name="clickableRow ? 'dt-row-clickable' : ''"
      :header-cell-style="headerCellStyle"
      @row-click="onRowClick"
      @selection-change="onSelectionChange"
      @sort-change="onSortChange"
    >
      <!-- 多选列：reserve-selection 让翻页/换数据后按 row-key 保持勾选 -->
      <el-table-column
        v-if="selectable"
        type="selection"
        width="44"
        reserve-selection
        :selectable="selectableFn"
      />

      <!-- 数据列 -->
      <el-table-column
        v-for="col in columns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
        :fixed="col.fixed"
        :align="col.align || 'left'"
        :sortable="col.sortable ? 'custom' : false"
        :show-overflow-tooltip="col.ellipsis !== false"
      >
        <template v-if="col.headerSlot || $slots['header-' + col.key]" #header>
          <slot :name="col.headerSlot || 'header-' + col.key" :column="col">
            {{ col.label }}
          </slot>
        </template>

        <template #default="scope">
          <!-- 有对应插槽就交给调用方渲染，否则走 formatter / 原始值 -->
          <slot
            v-if="col.slot || $slots['cell-' + col.key]"
            :name="col.slot || 'cell-' + col.key"
            :row="scope.row"
            :index="scope.$index"
            :value="scope.row[col.key]"
          />
          <span v-else-if="col.formatter">{{ col.formatter(scope.row) }}</span>
          <span v-else>{{ formatCell(scope.row[col.key]) }}</span>
        </template>
      </el-table-column>

      <!-- 空态：统一走 BaseEmptyState，避免各页各写一套 -->
      <template #empty>
        <slot name="empty">
          <BaseEmptyState compact :description="emptyText" />
        </slot>
      </template>
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * 表格（CH-042 二级组件）
 *
 * 为什么内部包 el-table 而不是继续自研 BaseTable：
 *   BaseTable 写了 264 行但零引用 —— 它缺固定列/展开行/tooltip，
 *   真要替换 el-table 会功能退化。这里把「列配置 + 统一空态 + 加载态」
 *   这层封装起来，内核仍用 el-table，能力不丢。
 */
import { ref } from 'vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import type { DataColumn, ListDensity } from './types'

const props = withDefaults(defineProps<{
  data: any[]
  columns: DataColumn[]
  rowKey?: string
  selectable?: boolean
  /** 行是否可点击（配合 row-click 用），会显示手型光标 */
  clickableRow?: boolean
  density?: ListDensity
  emptyText?: string
  /** 逐行控制是否可选，用于禁用某些行的勾选 */
  selectableFn?: (row: any, index: number) => boolean
}>(), {
  rowKey: 'id',
  selectable: false,
  clickableRow: false,
  density: 'compact',
  emptyText: '暂无数据',
  selectableFn: undefined,
})

const emit = defineEmits<{
  'selection-change': [rows: any[]]
  'row-click': [row: any, column: any, event: Event]
  'sort-change': [payload: { key: string; order: 'asc' | 'desc' | null }]
}>()

// 表头底色与列表外框一致，避免 el-table 默认灰底和卡片白底打架
const headerCellStyle = {
  background: 'var(--bg-elevated)',
  color: 'var(--text-secondary)',
  fontWeight: '600',
}

function formatCell(value: any): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function onSelectionChange(rows: any[]) {
  emit('selection-change', rows)
}

function onRowClick(row: any, column: any, event: Event) {
  if (!props.clickableRow) return
  emit('row-click', row, column, event)
}

function onSortChange(payload: { prop: string; order: 'ascending' | 'descending' | null }) {
  emit('sort-change', {
    key: payload.prop,
    order: payload.order === 'ascending' ? 'asc' : payload.order === 'descending' ? 'desc' : null,
  })
}

/**
 * 清空所有勾选。
 *
 * 为什么由组件提供而不是让父组件改数据：
 *   el-table 的多选状态是内部维护的，父组件清空自己的数组不会同步到表格，
 *   勾选框会留在选中态。必须调 el-table 的 clearSelection()。
 */
const tableRef = ref<any>(null)

function clearSelection() {
  tableRef.value?.clearSelection?.()
  emit('selection-change', [])
}

/**
 * 按 row-key 重新勾选指定行（CH-043）。
 *
 * 用途：批量操作后数据重新拉取，父组件知道「哪些还应该保持选中」，
 * 但 el-table 内部状态已经跟着新数据重置了，需要按 key 回填。
 *
 * 实现要点：先把当前表格里的行全部取消勾选，再逐行按 key 匹配勾上，
 * 避免残留旧勾选。匹配用 String 比较，防止 key 类型不一致（number vs string）。
 */
function setSelection(keys: (string | number)[]) {
  const table = tableRef.value
  if (!table) return
  table.clearSelection?.()
  const want = new Set((keys || []).map((k) => String(k)))
  if (!want.size) {
    emit('selection-change', [])
    return
  }
  const picked = (props.data || []).filter((row) => want.has(String(row[props.rowKey])))
  picked.forEach((row) => table.toggleRowSelection?.(row, true))
  emit('selection-change', picked)
}

defineExpose({ clearSelection, setSelection })
</script>

<style scoped>
.data-table {
  width: 100%;
}

/* 可点击行：光标 + 悬浮底色，与 Usage 现有交互一致 */
.data-table :deep(.dt-row-clickable) {
  cursor: pointer;
}

/*
 * el-table 默认外框是 1px 实线，这里去掉外层边框，
 * 让它嵌在 BaseSection 卡片里时不会出现「卡片里套一个方框」的观感。
 */
.data-table :deep(.el-table) {
  border-radius: var(--radius-sm);
}

.data-table :deep(.el-table::before) {
  display: none;
}

.data-table :deep(.el-table th.el-table__cell) {
  font-weight: 600;
}
</style>
