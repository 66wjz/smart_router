<template>
  <div class="filter-field" :style="width ? { width: typeof width === 'number' ? width + 'px' : width } : undefined">
    <label v-if="label" class="ff-label">{{ label }}</label>
    <div class="ff-control">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 筛选字段（CH-042 二级组件，配合 FilterBar 使用）
 *
 * 只做「标签 + 控件」的垂直排列，保证一排筛选框的标签与输入框基线对齐。
 */
withDefaults(defineProps<{
  label?: string
  /** 固定宽度，数字按 px 处理；不传则由内容撑开 */
  width?: number | string
}>(), {
  label: '',
  width: undefined,
})
</script>

<style scoped>
.filter-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.ff-label {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.ff-control {
  min-width: 0;
}

/* 控件统一高度，与 --control-height-sm 对齐，避免一排筛选框参差不齐 */
.ff-control :deep(.el-select),
.ff-control :deep(.el-input) {
  width: 100%;
}

.ff-control :deep(.el-select__wrapper),
.ff-control :deep(.el-input__wrapper) {
  min-height: var(--control-height-sm);
}
</style>
