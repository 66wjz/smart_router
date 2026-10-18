<template>
  <div class="modal-footer-actions">
    <div v-if="$slots.left" class="modal-footer-left">
      <slot name="left"></slot>
    </div>
    <BaseButton variant="ghost" :disabled="loading" @click="$emit('cancel')">
      {{ cancelText }}
    </BaseButton>
    <BaseButton v-if="showConfirm" :variant="confirmVariant" :disabled="loading || confirmDisabled"
      @click="$emit('confirm')">
      {{ loading ? loadingText : confirmText }}
    </BaseButton>
  </div>
</template>

<script setup lang="ts">
import BaseButton from './BaseButton.vue'

withDefaults(defineProps<{
  /** 保存中：按钮禁用 + 文案切换 */
  loading?: boolean
  confirmText?: string
  loadingText?: string
  cancelText?: string
  confirmVariant?: 'primary' | 'danger'
  /** 隐藏确定按钮（只读弹窗） */
  showConfirm?: boolean
  /** 业务条件不满足时禁用确定 */
  confirmDisabled?: boolean
}>(), {
  loading: false,
  confirmText: '保存',
  loadingText: '保存中…',
  cancelText: '取消',
  confirmVariant: 'primary',
  showConfirm: true,
  confirmDisabled: false,
})

defineEmits<{
  cancel: []
  confirm: []
}>()
</script>

<style scoped>
.modal-footer-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  /* 占满 footer 宽度，左侧附加操作才能靠到弹窗左边（CH-028） */
  width: 100%;
}
/* 左侧附加操作（如「重新加载」）靠左，右侧仍保持取消+确定 */
.modal-footer-left {
  margin-right: auto;
}
</style>
