<template>
  <label class="base-checkbox" :class="{ disabled, checked: modelValue }">
    <input
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      :indeterminate="indeterminate"
      class="base-checkbox-input"
      @change="onChange"
    />
    <span v-if="$slots.default" class="base-checkbox-label">
      <slot />
    </span>
  </label>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue?: boolean
  disabled?: boolean
  indeterminate?: boolean
}>(), {
  modelValue: false,
  disabled: false,
  indeterminate: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

function onChange(e: Event) {
  if (props.disabled) return
  emit('update:modelValue', (e.target as HTMLInputElement).checked)
}
</script>

<style scoped>
.base-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
}

.base-checkbox.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.base-checkbox-input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-blue);
  cursor: pointer;
  flex-shrink: 0;
}

.base-checkbox.disabled .base-checkbox-input {
  cursor: not-allowed;
}

.base-checkbox-label {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1;
}
</style>
