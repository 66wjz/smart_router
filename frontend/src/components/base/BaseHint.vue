<template>
  <component :is="inline ? 'span' : 'p'"
    class="base-hint"
    :class="{
      'base-hint-block': block,
      'base-hint-inline': inline,
      'base-hint-warn': variant === 'warn',
    }">
    <slot>{{ text }}</slot>
  </component>
</template>

<script setup lang="ts">
/**
 * 说明文字（统一替代散落的 el-text type="info" 与临时 .hint class）
 *
 * 三种版式：
 *   默认    → 独占一行的段落（margin-top 4px）
 *   block   → 独占一行且上方留白（margin-top 8px）
 *   inline  → 跟在控件后面的行内文字（margin-left 8px）
 */
withDefaults(defineProps<{
  /** 纯文本快捷写法（也可用默认插槽） */
  text?: string
  /** 独占一行且上方留白 */
  block?: boolean
  /** 跟在控件后面（行内） */
  inline?: boolean
  variant?: 'info' | 'warn'
}>(), {
  text: '',
  block: false,
  inline: false,
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
.base-hint-inline {
  margin: 0 0 0 8px;
  display: inline;
}
.base-hint-warn {
  color: var(--accent-amber);
}
</style>
