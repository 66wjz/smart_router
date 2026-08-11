<template>
  <div class="base-table-wrapper">
    <table class="base-table" :class="'density-' + density">
      <colgroup>
        <col v-if="selectable" style="width: 40px" />
        <col v-for="col in visibleColumns" :key="col.key" :style="getColStyle(col)" />
      </colgroup>
      <thead>
        <tr>
          <th v-if="selectable" class="col-selection">
            <BaseCheckbox :model-value="isAllSelected" :indeterminate="isIndeterminate" @update:model-value="toggleAll" />
          </th>
          <th v-for="col in visibleColumns" :key="col.key"
            :class="{ sortable: col.sortable }"
            @click="onHeaderClick(col)">
            <slot :name="'header-' + col.key">{{ col.label }}</slot>
            <span v-if="col.sortable && sortKey === col.key" class="sort-indicator">
              {{ sortOrder === 'asc' ? '↑' : '↓' }}
            </span>
            <span v-else-if="col.sortable" class="sort-indicator sort-inactive">⇅</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in data" :key="rowKey ? row[rowKey] : index"
          :class="{ 'row-selected': selectable && selectedSet.has(rowKey ? row[rowKey] : index) }">
          <td v-if="selectable" class="col-selection">
            <BaseCheckbox :model-value="selectedSet.has(rowKey ? row[rowKey] : index)" @update:model-value="toggleRow(rowKey ? row[rowKey] : index)" />
          </td>
          <td v-for="col in visibleColumns" :key="col.key"
            :class="{ 'td-ellipsis': col.ellipsis === true }">
            <slot :name="'cell-' + col.key" :row="row" :index="index">
              {{ row[col.key] }}
            </slot>
          </td>
        </tr>
        <tr v-if="data.length === 0">
          <td :colspan="(selectable ? 1 : 0) + visibleColumns.length" class="base-table-empty">
            <slot name="empty">暂无数据</slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import BaseCheckbox from './BaseCheckbox.vue'

interface Column {
  key: string
  label: string
  width?: string
  minWidth?: string
  maxWidth?: string
  sortable?: boolean
  ellipsis?: boolean
  align?: 'left' | 'center' | 'right'
  fixed?: 'left' | 'right'
}

const props = withDefaults(defineProps<{
  columns: Column[]
  data: any[]
  rowKey?: string
  selectable?: boolean
  density?: 'compact' | 'default' | 'loose'
  modelValue?: (string | number)[]
}>(), {
  rowKey: 'id',
  selectable: false,
  density: 'default',
  modelValue: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: (string | number)[]]
  'sort-change': [key: string, order: 'asc' | 'desc' | null]
  'selection-change': [ids: (string | number)[]]
}>()

const visibleColumns = computed(() => props.columns)

// Selection
const selectedSet = computed(() => new Set(props.modelValue))

const isAllSelected = computed(() => {
  if (props.data.length === 0) return false
  return props.data.every(row => selectedSet.value.has(row[props.rowKey]))
})

const isIndeterminate = computed(() => {
  const count = props.data.filter(row => selectedSet.value.has(row[props.rowKey])).length
  return count > 0 && count < props.data.length
})

function toggleAll() {
  if (isAllSelected.value) {
    emit('update:modelValue', [])
    emit('selection-change', [])
  } else {
    const ids = props.data.map(row => row[props.rowKey])
    emit('update:modelValue', ids)
    emit('selection-change', ids)
  }
}

function toggleRow(id: string | number) {
  const current = [...props.modelValue]
  const idx = current.indexOf(id)
  if (idx >= 0) {
    current.splice(idx, 1)
  } else {
    current.push(id)
  }
  emit('update:modelValue', current)
  emit('selection-change', current)
}

// Sort
const sortKey = ref<string | null>(null)
const sortOrder = ref<'asc' | 'desc' | null>(null)

// colgroup 的 <col> 样式：控制列宽分配
function getColStyle(col: Column) {
  const style: Record<string, string> = {}
  if (col.width) {
    style.width = col.width
  } else {
    // 无 width 的列设为 auto，浏览器将剩余空间均分给这些列
    style.width = 'auto'
  }
  if (col.minWidth) style.minWidth = col.minWidth
  if (col.maxWidth) style.maxWidth = col.maxWidth
  return style
}

function onHeaderClick(col: Column) {
  if (!col.sortable) return
  if (sortKey.value !== col.key) {
    sortKey.value = col.key
    sortOrder.value = 'asc'
  } else if (sortOrder.value === 'asc') {
    sortOrder.value = 'desc'
  } else {
    sortKey.value = null
    sortOrder.value = null
  }
  emit('sort-change', sortKey.value!, sortOrder.value!)
}
</script>

<style scoped>
.base-table-wrapper {
  overflow-x: auto;
  background: #fff;
  border-radius: var(--radius-md);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.base-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 500px;
  table-layout: fixed;
}

/* Density variants */
.base-table.density-compact th,
.base-table.density-compact td { padding: 6px 10px; font-size: 13px; }
.base-table.density-default th,
.base-table.density-default td { padding: 10px 14px; font-size: 14px; }
.base-table.density-loose th,
.base-table.density-loose td { padding: 14px 16px; font-size: 14px; }

.base-table th,
.base-table td {
  text-align: left;
  border-bottom: 1px solid var(--border-subtle);
  overflow: hidden;
}

.base-table th {
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  position: sticky;
  top: 0;
  user-select: none;
}

.base-table th.sortable {
  cursor: pointer;
}
.base-table th.sortable:hover {
  background: var(--bg-hover);
}

/* td 截断：ellipsis 默认开启，通过 class 控制 */
.base-table td.td-ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sort-indicator {
  margin-left: 4px;
  font-size: 12px;
  color: var(--accent-blue);
}
.sort-inactive {
  color: var(--text-tertiary);
  opacity: 0.5;
}

.col-selection {
  text-align: center !important;
  width: 40px;
}

.base-table tbody tr:hover {
  background: var(--bg-hover);
}
.base-table tbody tr.row-selected {
  background: var(--bg-hover);
}

.base-table tbody tr:last-child td {
  border-bottom: none;
}

.base-table td code {
  font-size: 12px;
  padding: 2px 6px;
  background: var(--bg-elevated);
  border-radius: 4px;
  word-break: break-all;
  font-family: 'Menlo', 'Consolas', monospace;
}

/* Action icon buttons */
.action-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm, 4px);
  transition: all 0.15s;
}
.action-icon:hover {
  background: var(--bg-hover);
  color: var(--accent-blue);
}
.action-icon.danger:hover {
  background: var(--bg-hover);
  color: var(--accent-red);
}

.action-icon + .action-icon {
  margin-left: 4px;
}

/* More actions dropdown trigger */
.action-more-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm, 4px);
  transition: all 0.15s;
}
.action-more-btn:hover {
  background: var(--bg-hover);
}

.base-table-empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-tertiary);
  font-size: 14px;
}
</style>
