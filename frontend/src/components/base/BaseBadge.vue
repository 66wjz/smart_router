<template>
  <span :class="badgeClass">
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'default' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'gray'
}>(), {
  variant: 'default'
})

const badgeClass = computed(() => [
  'base-badge',
  `base-badge-${props.variant}`
])
</script>

<style scoped>
.base-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.base-badge-default {
  background: var(--bg-elevated);
  color: var(--text-secondary);
}
.base-badge-gray {
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}
.base-badge-blue {
  background: var(--accent-blue-muted);
  color: var(--accent-blue);
}
.base-badge-green {
  background: var(--accent-green-muted);
  color: var(--accent-green);
}
.base-badge-amber {
  background: var(--accent-amber-muted);
  color: var(--accent-amber);
}
.base-badge-red {
  background: var(--accent-red-muted);
  color: var(--accent-red);
}
.base-badge-purple {
  background: var(--accent-purple-muted);
  color: var(--accent-purple);
}
</style>
