<template>
  <div v-if="visible" class="base-notice" :class="'base-notice-' + variant">
    <BaseIcon class="base-notice-icon" :name="iconName" :size="16" />
    <div class="base-notice-body">
      <div v-if="title" class="base-notice-title">{{ title }}</div>
      <div class="base-notice-text"><slot>{{ text }}</slot></div>
    </div>
    <button v-if="closable" class="base-notice-close" type="button" @click="visible = false">
      <BaseIcon name="x" :size="14" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseIcon from './BaseIcon.vue'

const props = withDefaults(defineProps<{
  /** 单行文案；需要富文本时用默认插槽 */
  title?: string
  text?: string
  variant?: 'info' | 'warning' | 'error' | 'success'
  /** 可关闭（默认不可关，与页面级说明条一致） */
  closable?: boolean
}>(), {
  title: '',
  text: '',
  variant: 'info',
  closable: false,
})

const visible = defineModel<boolean>('visible', { default: true })

const iconName = computed(() => ({
  info: 'info',
  warning: 'alert-triangle',
  error: 'x-circle',
  success: 'check-circle',
}[props.variant]))
</script>

<style scoped>
.base-notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 12px;
}
.base-notice-icon {
  flex-shrink: 0;
  margin-top: 2px;
}
.base-notice-body {
  flex: 1;
  min-width: 0;
}
.base-notice-close {
  flex-shrink: 0;
  background: none;
  border: none;
  padding: 2px;
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  border-radius: var(--radius-sm);
}
.base-notice-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.base-notice-title {
  font-weight: 500;
  margin-bottom: 2px;
}
.base-notice-text {
  color: var(--text-secondary);
}
.base-notice-info { background: var(--accent-blue-muted); }
.base-notice-warning { background: var(--accent-amber-muted); }
.base-notice-error { background: var(--accent-red-muted); }
.base-notice-success { background: var(--accent-green-muted); }
</style>
