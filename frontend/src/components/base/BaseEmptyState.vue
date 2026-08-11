<template>
  <div class="base-empty-state">
    <div v-if="icon" class="base-empty-icon">{{ icon }}</div>
    <p v-if="title" class="base-empty-title">{{ title }}</p>
    <p v-if="description" class="base-empty-desc">{{ description }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  icon?: string
  title?: string
  description?: string
}>(), {
  icon: '',
  title: '',
  description: '',
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
</style>
