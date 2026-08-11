<template>
  <div v-if="visible" class="base-alert" :class="['base-alert-' + variant]">
    <div class="base-alert-content">
      <BaseIcon v-if="variant === 'info'" class="base-alert-icon" name="info" :size="16" />
      <BaseIcon v-else-if="variant === 'warning'" class="base-alert-icon" name="alert-triangle" :size="16" />
      <BaseIcon v-else-if="variant === 'error'" class="base-alert-icon" name="x-circle" :size="16" />
      <BaseIcon v-else class="base-alert-icon" name="check-circle" :size="16" />
      <span class="base-alert-text"><slot></slot></span>
    </div>
    <button v-if="closable" class="base-alert-close" @click="visible = false">
      <BaseIcon name="x" :size="14" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import BaseIcon from './BaseIcon.vue'

withDefaults(defineProps<{
  variant?: 'info' | 'warning' | 'error' | 'success'
  title?: string
  closable?: boolean
}>(), {
  variant: 'info',
  title: '',
  closable: false
})

const visible = ref(true)
</script>

<style scoped>
.base-alert { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-radius: var(--radius-sm); font-size: 13px; margin-bottom: 12px; }
.base-alert-content { display: flex; align-items: center; gap: 8px; }
.base-alert-icon { flex-shrink: 0; }
.base-alert-text { color: var(--text-primary); line-height: 1.5; }
.base-alert-close { background: none; border: none; color: var(--text-tertiary); cursor: pointer; padding: 2px; display: flex; align-items: center; border-radius: var(--radius-sm); }
.base-alert-close:hover { background: var(--bg-hover); color: var(--text-primary); }
.base-alert-info { background: var(--accent-blue-muted); color: var(--accent-blue); border: 1px solid transparent; }
.base-alert-warning { background: var(--accent-amber-muted); color: var(--accent-amber); border: 1px solid transparent; }
.base-alert-error { background: var(--accent-red-muted); color: var(--accent-red); border: 1px solid transparent; }
.base-alert-success { background: var(--accent-green-muted); color: var(--accent-green); border: 1px solid transparent; }
</style>
