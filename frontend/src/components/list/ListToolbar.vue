<template>
  <div class="list-toolbar">
    <!-- 左侧：未选中显示总数，选中后显示已选 -->
    <div class="lt-info">
      <!--
        快捷全选（CH-045）：卡片列表没有 el-table 表头，所以全选框放在工具条左侧。
        语义与表格表头全选一致 —— 只作用于「当前页」。
      -->
      <el-checkbox
        v-if="selectable"
        class="lt-check-all"
        :model-value="allChecked"
        :indeterminate="indeterminate"
        :disabled="!total"
        @change="(v: any) => $emit('toggle-all', Boolean(v))"
      >
        <span class="lt-all-label">全选</span>
      </el-checkbox>

      <template v-if="count > 0">
        <BaseIcon name="check-circle" :size="14" class="lt-checked" />
        <span class="lt-count">{{ countLabel }} {{ count }} 项</span>
        <button type="button" class="lt-clear" @click="$emit('clear')">取消选择</button>
      </template>
      <template v-else>
        <span class="lt-total">
          共 <b>{{ total }}</b> 条
          <template v-if="summary"> · {{ summary }}</template>
        </span>
      </template>
    </div>

    <!--
      右侧：批量操作 + 批量导出 + 导出全部

      三条约定（用户 2026-10-21 明确）：
        1. 批量按钮**始终显示**，未选中时置灰禁用 —— 不靠 v-if 隐藏，避免工具条高度跳动
        2. 顺序固定：批量操作 → 批量导出 → 导出（批量在前，导出全部在后）
        3. 批量按钮与导出之间**不加分割线**，整条更干净
    -->
    <div class="lt-actions">
      <BaseButton
        v-for="(a, i) in actions"
        :key="`${a.label}-${i}`"
        :variant="a.variant || 'ghost'"
        size="sm"
        :disabled="count === 0 || a.disabled"
        @click="a.onClick"
      >
        {{ a.label }}
      </BaseButton>

      <slot />

      <BaseButton
        v-if="dataset && batchExport"
        variant="ghost"
        size="sm"
        :disabled="count === 0 || exporting"
        @click="handleExportBatch"
      >
        批量导出
      </BaseButton>

      <BaseButton
        v-if="dataset"
        variant="ghost"
        size="sm"
        :disabled="exporting"
        @click="handleExportAll"
      >
        <BaseIcon name="download" :size="13" />
        导出
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 列表工具条（CH-042 二级组件）
 *
 * 设计要点：
 *   1. **常驻**：不随选中状态显隐。未选中时左侧显示「共 N 条」，
 *      这样没有任何批量操作的列表（如用量明细）也有统一的一条工具条承载导出。
 *   2. **灰底不蓝底**：与筛选区同一色调（--bg-elevated），避免一页两块蓝抢视线。
 *   3. **批量按钮常显 + 未选中禁用**：按钮位置稳定，用户能预先看到有哪些批量能力。
 *   4. 导出分两档：`批量导出`（选中项）在前，`导出`（全部）在后。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import { exportAll, exportBatch, type ExportDataset } from '@/api/export'
import type { RowActionItem } from './types'

const props = withDefaults(defineProps<{
  /** 已选数量；0 表示未选中任何行 */
  count?: number
  countLabel?: string
  /** 未选中时显示的「共 N 条」 */
  total?: number
  /** 未选中时的补充说明，如「已启用 5 个」 */
  summary?: string
  /** 批量操作按钮；未选中时自动禁用 */
  actions?: RowActionItem[]
  /** 后端导出数据集标识；不传则不显示导出按钮 */
  dataset?: ExportDataset
  /** 是否支持批量导出（列表有多选框时才开） */
  batchExport?: boolean
  /** 导出时附带的筛选参数（如用量页的 range） */
  exportParams?: Record<string, string>
  /** 批量导出要提交的 id 列表 */
  selectedIds?: string[]
  /** 是否显示「全选」勾选框（卡片列表没有表头，靠它做快捷全选） */
  selectable?: boolean
  /** 当前页是否已全选 */
  allChecked?: boolean
  /** 当前页部分选中（半选态） */
  indeterminate?: boolean
}>(), {
  count: 0,
  countLabel: '已选',
  total: 0,
  summary: '',
  actions: () => [],
  dataset: undefined,
  batchExport: false,
  exportParams: () => ({}),
  selectedIds: () => [],
  selectable: false,
  allChecked: false,
  indeterminate: false,
})

defineEmits<{
  /** 点「取消选择」时通知父组件清空选中 */
  clear: []
  /** 点「全选」时通知父组件切换当前页选中 */
  'toggle-all': [value: boolean]
}>()

const exporting = ref(false)

async function handleExportAll() {
  if (!props.dataset) return
  exporting.value = true
  try {
    await exportAll(props.dataset, props.exportParams)
    ElMessage.success('已开始下载')
  } catch {
    /* 错误提示已在 api/export 的拦截器里统一处理 */
  } finally {
    exporting.value = false
  }
}

async function handleExportBatch() {
  if (!props.dataset) return
  if (!props.selectedIds.length) {
    ElMessage.warning('请先勾选要导出的记录')
    return
  }
  exporting.value = true
  try {
    await exportBatch(props.dataset, props.selectedIds)
    ElMessage.success(`已导出选中的 ${props.selectedIds.length} 条`)
  } catch {
    /* 同上 */
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.list-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  margin-bottom: 10px;
  border-radius: var(--radius-sm);
  /* 与筛选区同色系，不用蓝色 */
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  flex-wrap: wrap;
}

.lt-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  min-height: var(--control-height-sm);
}

/* 快捷全选：与左侧计数分隔开，避免和「已选 N 项」粘在一起 */
.lt-check-all {
  margin-right: 4px;
  padding-right: 12px;
  border-right: 1px solid var(--border-subtle);
}

.lt-all-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.lt-checked {
  color: var(--accent-blue);
}

.lt-count {
  font-weight: 600;
  color: var(--text-primary);
}

.lt-total b {
  color: var(--text-primary);
  font-weight: 600;
}

.lt-clear {
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
  color: var(--accent-blue);
  cursor: pointer;
}

.lt-clear:hover {
  color: var(--accent-blue-hover);
  text-decoration: underline;
}

.lt-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  flex-wrap: wrap;
}
</style>
