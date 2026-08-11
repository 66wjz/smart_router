<template>
  <label class="base-check-tag" :class="{ checked: modelValue, sm: size === 'sm' }" :title="title">
    <input
      type="checkbox"
      :checked="modelValue"
      @change="emit('update:modelValue', ($event.target as HTMLInputElement).checked)"
    />
    <svg v-if="modelValue" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
    <span class="base-check-tag-label"><slot /></span>
  </label>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  size?: 'default' | 'sm'
}>(), {
  title: '',
  size: 'default'
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()
</script>

<style scoped>
.base-check-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 10px;
  height: var(--control-height);
  background: var(--bg-base);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  user-select: none;
  transition: all var(--duration-fast);
}

.base-check-tag:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.base-check-tag.checked {
  /* 方案A：白底 + 蓝色细边框 + 蓝 ✓ 蓝字，不用蓝填充 */
  background: var(--bg-base);
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

/* 原生复选框隐藏，选中态用 ✓ 图标表达 */
.base-check-tag input[type="checkbox"] {
  display: none;
}

.base-check-tag svg {
  flex-shrink: 0;
}

.base-check-tag.sm {
  height: var(--control-height-sm);
  padding: 0 8px;
  font-size: 11px;
}
</style>
