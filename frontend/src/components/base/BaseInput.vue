<template>
  <textarea
    v-if="type === 'textarea'"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :maxlength="maxlength"
    class="base-input base-textarea"
    :class="sizeClass"
    @input="onInput"
    @focus="$emit('focus', $event)"
    @blur="$emit('blur', $event)"
    @keydown="$emit('keydown', $event)"
    v-bind="$attrs"
  />
  <input
    v-else
    :type="type"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :maxlength="maxlength"
    class="base-input"
    :class="sizeClass"
    @input="onInput"
    @focus="$emit('focus', $event)"
    @blur="$emit('blur', $event)"
    @keydown="$emit('keydown', $event)"
    v-bind="$attrs"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue?: string | number
  type?: string
  placeholder?: string
  disabled?: boolean
  maxlength?: number | string
  size?: 'default' | 'sm' | 'lg'
}>(), {
  modelValue: '',
  type: 'text',
  placeholder: '',
  disabled: false,
  size: 'default',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'focus': [event: FocusEvent]
  'blur': [event: FocusEvent]
  'keydown': [event: KeyboardEvent]
}>()

const sizeClass = computed(() => ({
  'base-input-sm': props.size === 'sm',
  'base-input-lg': props.size === 'lg',
}))

function onInput(e: Event) {
  const target = e.target as HTMLInputElement | HTMLTextAreaElement
  emit('update:modelValue', target.value)
}
</script>

<style scoped>
.base-input {
  width: 100%;
  padding: 0 12px;
  height: var(--control-height);
  background: var(--bg-base);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color var(--duration-fast);
  box-sizing: border-box;
}

.base-input:focus {
  border-color: var(--accent-blue);
}

.base-input::placeholder {
  color: var(--text-tertiary);
}

.base-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.base-input-sm {
  padding: 0 8px;
  font-size: 13px;
  height: var(--control-height-sm);
}

.base-input-lg {
  padding: 0 16px;
  font-size: 15px;
  height: var(--control-height-lg);
}

.base-textarea {
  min-height: 80px;
  resize: vertical;
}

.base-textarea.base-input-sm {
  min-height: 60px;
  height: auto;
}

.base-textarea.base-input-lg {
  min-height: 100px;
}
</style>
