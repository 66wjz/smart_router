<template>
  <div class="filter-bar">
    <div class="fb-fields">
      <slot />
    </div>
    <div class="fb-actions">
      <BaseButton variant="primary" size="sm" :disabled="loading" @click="$emit('search')">
        <BaseIcon v-if="!loading" name="search" :size="13" />
        {{ loading ? '查询中…' : '查询' }}
      </BaseButton>
      <BaseButton variant="ghost" size="sm" :disabled="loading" @click="$emit('reset')">
        <BaseIcon name="rotate-ccw" :size="13" />
        重置
      </BaseButton>
      <slot name="extra" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 筛选区（CH-042 二级组件）
 *
 * 字段用 FilterField 包裹后塞进默认插槽，自动横排 + 窄屏换行。
 * 只负责「排版 + 两个标准按钮」，不关心具体有哪些字段。
 */
import BaseButton from '@/components/base/BaseButton.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'

withDefaults(defineProps<{
  loading?: boolean
}>(), {
  loading: false,
})

defineEmits<{
  search: []
  reset: []
}>()
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 14px;
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
  flex-wrap: wrap;
}

.fb-fields {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.fb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
  .fb-actions {
    justify-content: flex-end;
  }
}
</style>
