<template>
  <div class="base-card" :class="[variantClasses, { 'is-default': isDefault }]">
    <slot></slot>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'default' | 'system' | 'hoverable'
  isDefault?: boolean
}>(), {
  variant: 'default',
  isDefault: false
})

const variantClasses = computed(() => {
  return {
    'base-card-system': props.variant === 'system',
    'base-card-hoverable': props.variant === 'hoverable'
  }
})
</script>

<style scoped>
.base-card {
  padding: 16px;
  background: var(--bg-base);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  margin-bottom: 8px;
  transition: all var(--duration-fast);
}

.base-card:hover {
  border-color: var(--border-subtle);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.base-card-hoverable:hover,
.base-card-system:hover {
  border-color: var(--border-subtle);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.base-card.is-default {
  /* 方案A：白底 + 左侧蓝色强调边框（边框天然跟随圆角，左内边距减 2px 补偿加粗的边框） */
  border-color: var(--border-subtle);
  border-left: 3px solid var(--accent-blue);
  background: var(--bg-base);
  padding-left: 14px;
}
</style>