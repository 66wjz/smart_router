<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" :style="zStyle" @click.self="handleClose">
      <div class="modal-box" :class="[sizeClasses]" :style="boxStyle" @click.stop>
        <div class="modal-header">
          <h3>{{ title }}</h3>
          <button class="modal-close" @click="handleClose">
            <BaseIcon name="x" :size="16" />
          </button>
        </div>
        <div class="modal-body">
          <slot></slot>
        </div>
        <div v-if="$slots.footer" class="modal-footer">
          <slot name="footer"></slot>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseIcon from './BaseIcon.vue'

/**
 * layer 层级映射:
 *   'modal'  → --z-modal (2000)  普通弹窗
 *   'nested' → --z-modal-nested (2100)  弹窗内再弹出的弹窗
 */
const Z_LAYER_MAP: Record<string, string> = {
  modal: 'var(--z-modal)',
  nested: 'var(--z-modal-nested)',
}

const props = withDefaults(defineProps<{
  visible: boolean
  title: string
  size?: 'default' | 'wide' | 'large'
  layer?: 'modal' | 'nested'
  height?: string
}>(), {
  size: 'default',
  layer: 'modal'
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const sizeClasses = computed(() => {
  return {
    'modal-wide': props.size === 'wide',
    'modal-lg': props.size === 'large'
  }
})

const boxStyle = computed(() => {
  if (!props.height) return {}
  return { height: props.height, maxHeight: props.height }
})

const zStyle = computed(() => ({
  zIndex: Z_LAYER_MAP[props.layer] || Z_LAYER_MAP['modal']
}))

function handleClose() {
  emit('update:visible', false)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

.modal-box {
  background: var(--bg-base);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  min-width: 420px;
  max-width: 520px;
  max-height: 80vh;
  padding: 24px;
  animation: slideUp 0.2s ease;
  display: flex;
  flex-direction: column;
  position: relative;
}

.modal-box.modal-wide {
  min-width: 520px;
  max-width: 620px;
}

.modal-box.modal-lg {
  min-width: 600px;
  max-width: 720px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.modal-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast);
}

.modal-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 20px;
  position: relative;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

/* 弹窗底部按钮统一使用小尺寸（与 sm 一致） */
.modal-footer :deep(.btn) {
  padding: 4px 10px;
  font-size: 12px;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
