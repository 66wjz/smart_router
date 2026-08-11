<template>
  <div class="base-section" :class="{ 'base-section-card': variant === 'card' }">
    <div v-if="title || $slots.header" class="section-header">
      <div class="section-title-wrapper">
        <slot name="header">
          <h4>{{ title }}</h4>
        </slot>
      </div>
      <div v-if="actions || $slots.actions" class="section-actions">
        <slot name="actions">
          <component v-if="actions" :is="actions" />
        </slot>
      </div>
    </div>
    <div v-if="description" class="section-description">{{ description }}</div>
    <div class="section-body">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  description?: string
  actions?: any
  /** 显示模式：default 无底板，card 白色底板+微阴影 */
  variant?: 'default' | 'card'
}>(), {
  title: '',
  description: '',
  variant: 'default'
})
</script>

<style scoped>
.base-section {
  margin-bottom: 32px;
  padding-top: 24px;
  position: relative;
}

.base-section::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--border-subtle);
}

/* card 变体：白色底板+微阴影+圆角，隐藏顶部分隔线 */
.base-section-card {
  background: var(--bg-base);
  border-radius: var(--radius-md);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 24px;
  padding-top: 24px;
}

.base-section-card::before {
  display: none;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.section-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title-wrapper h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-description {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-body {
  padding-top: 4px;
}
</style>