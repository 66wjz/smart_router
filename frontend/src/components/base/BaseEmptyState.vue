<template>
  <div class="base-empty-state" :class="{ 'base-empty-compact': compact }">
    <div v-if="icon" class="base-empty-icon">{{ icon }}</div>
    <p v-if="title" class="base-empty-title">{{ title }}</p>
    <p v-if="description" class="base-empty-desc">{{ description }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
/**
 * 空态 / 空占位
 *
 * 两种密度：
 *   默认    → 页面级空态（大留白 + 图标）
 *   compact → 区块内小块空态（如图表无数据、卡片内无成员）
 */
withDefaults(defineProps<{
  icon?: string
  title?: string
  description?: string
  /** 紧凑模式：用于区块内的小块占位，减少上下留白与字号 */
  compact?: boolean
}>(), {
  icon: '',
  title: '',
  description: '',
  compact: false,
})
</script>

<style scoped>
.base-empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-tertiary);
}
.base-empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}
.base-empty-title {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 4px;
}
.base-empty-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
}

/* 紧凑：区块内小块占位 */
.base-empty-compact {
  padding: 16px 0;
  text-align: left;
}
.base-empty-compact .base-empty-icon {
  font-size: 24px;
  margin-bottom: 6px;
}
.base-empty-compact .base-empty-title {
  font-size: 13px;
}
.base-empty-compact .base-empty-desc {
  font-size: 12px;
}
</style>
