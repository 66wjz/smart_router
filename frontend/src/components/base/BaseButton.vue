<template>
  <button
    :class="buttonClasses"
    :disabled="disabled"
    type="button"
    v-bind="$attrs"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Variant = 'primary' | 'ghost' | 'danger' | 'secondary' | 'icon'
type Size = 'default' | 'sm' | 'lg'

const props = withDefaults(defineProps<{
  variant?: Variant
  size?: Size
  block?: boolean
  disabled?: boolean
}>(), {
  variant: 'ghost',
  size: 'default',
  block: false,
  disabled: false,
})

const buttonClasses = computed(() => [
  'btn',
  `btn-${props.variant}`,
  props.size !== 'default' && `btn-${props.size}`,
  props.block && 'btn-block',
])
</script>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 16px;
  height: var(--control-height);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: 13px;
  box-sizing: border-box;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--duration-fast);
  white-space: nowrap;
}

.btn:active { transform: scale(0.97); }

.btn-primary {
  background: var(--accent-blue);
  color: #ffffff;
  border-color: var(--accent-blue);
}
.btn-primary:hover { background: var(--accent-blue-hover); border-color: var(--accent-blue-hover); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-ghost {
  background: transparent;
  color: var(--text-primary);
  border-color: var(--border-default);
}
.btn-ghost:hover { background: var(--bg-hover); border-color: var(--border-emphasis); }

.btn-danger {
  background: var(--accent-red-muted);
  color: var(--accent-red);
  border-color: transparent;
}
.btn-danger:hover { background: var(--accent-red); color: #fff; }

.btn-secondary {
  background: var(--bg-base);
  border-color: var(--border-default);
  color: var(--text-secondary);
}
.btn-secondary:hover { border-color: var(--border-emphasis); color: var(--text-primary); }

.btn-icon {
  background: none;
  border: none;
  color: var(--text-secondary);
  padding: 6px;
  border-radius: var(--radius-sm);
}
.btn-icon:hover { background: var(--bg-hover); color: var(--text-primary); }
.btn-icon:active { background: var(--bg-hover); }

.btn-sm { padding: 0 10px; font-size: 12px; height: var(--control-height-sm); }
.btn-lg { padding: 0 24px; font-size: 15px; height: var(--control-height-lg); }
.btn-block { width: 100%; }
</style>
