<template>
  <div class="table-pagination">
    <span class="tp-total">共 {{ total }} 条</span>

    <el-select
      :model-value="pageSize"
      class="tp-size"
      size="small"
      @change="onSizeChange"
    >
      <el-option
        v-for="s in pageSizes"
        :key="s"
        :label="`${s} 条/页`"
        :value="s"
      />
    </el-select>

    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      :layout="showJumper ? 'prev, pager, next, jumper' : 'prev, pager, next'"
      :pager-count="5"
      size="small"
      @current-change="onPageChange"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 列表分页（CH-042 二级组件）
 *
 * 为什么不用 BasePagination：
 *   BasePagination 的 layout 写死为 `prev, pager, next, total`，没有
 *   「共 N 条 / 每页条数 / 前往第 X 页」。这里按列表页的通用形态重做一份，
 *   BasePagination 保持原样不动（Usage 页仍在用）。
 */
withDefaults(defineProps<{
  page: number
  pageSize: number
  total: number
  pageSizes?: number[]
  /** 是否显示「前往 X 页」，窄屏可关掉 */
  showJumper?: boolean
}>(), {
  pageSizes: () => [20, 50, 100],
  showJumper: true,
})

const emit = defineEmits<{
  'update:page': [value: number]
  'update:pageSize': [value: number]
  /** 页码或每页条数变化后统一抛一次，便于调用方只写一个 load() */
  change: []
}>()

function onPageChange(value: number) {
  emit('update:page', value)
  emit('change')
}

function onSizeChange(value: number) {
  emit('update:pageSize', value)
  // 换每页条数后回到第一页，避免落在超出范围的页码上
  emit('update:page', 1)
  emit('change')
}
</script>

<style scoped>
.table-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 14px;
  flex-wrap: wrap;
}

.tp-total {
  font-size: 13px;
  color: var(--text-secondary);
}

.tp-size {
  width: 108px;
}

/* Element Plus 分页在 small 下的间距微调，与列表密度对齐 */
.table-pagination :deep(.el-pagination) {
  padding: 0;
  font-weight: 400;
}

@media (max-width: 768px) {
  .table-pagination {
    justify-content: flex-start;
  }
}
</style>
