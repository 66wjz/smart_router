<template>
  <div class="row-actions">
    <template v-for="(item, i) in items" :key="i">
      <span v-if="item.divider" class="ra-divider" />
      <BaseButton
        :variant="item.variant || 'ghost'"
        size="sm"
        :disabled="item.disabled"
        @click="item.onClick"
      >
        {{ item.label }}
      </BaseButton>
    </template>
    <slot />
  </div>
</template>

<script setup lang="ts">
/**
 * 行内操作组（CH-042 二级组件）
 *
 * 解决现状：`.row-actions` / `.rule-actions` / `.upstream-actions` /
 * `.model-ops` / `.batch-ops` 五套类名，全是「横排按钮 gap 8px」。
 *
 * 两种用法：
 *   1) 传 items 数组（推荐，纯配置）
 *   2) 默认插槽直接放 BaseButton
 */
import BaseButton from '@/components/base/BaseButton.vue'
import type { RowActionItem } from './types'

withDefaults(defineProps<{
  items?: RowActionItem[]
}>(), {
  items: () => [],
})
</script>

<style scoped>
.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.ra-divider {
  width: 1px;
  height: 14px;
  background: var(--border-subtle);
  flex-shrink: 0;
}
</style>
