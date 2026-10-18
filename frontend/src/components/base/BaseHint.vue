<template>
  <p class="base-hint" :class="{ 'base-hint-block': block, 'base-hint-warn': variant === 'warn' }">
    <slot>{{ text }}</slot>
  </p>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  /** 纯文本快捷写法（也可用默认插槽） */
  text?: string
  /** 是否独占一行（默认 inline-block 跟在控件下方） */
  block?: boolean
  variant?: 'info' | 'warn'
}>(), {
  text: '',
  block: false,
  variant: 'info',
})
</script>

<style scoped>
.base-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.5;
  margin: 4px 0 0;
}
.base-hint-block {
  margin-top: 8px;
}
.base-hint-warn {
  color: var(--accent-amber);
}
</style>
