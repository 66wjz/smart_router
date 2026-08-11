<template>
  <div class="base-spinner-wrap" :class="{ centered }">
    <div class="base-spinner" :class="sizeClass"></div>
    <span v-if="text" class="base-spinner-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  size?: 'sm' | 'md' | 'lg'
  text?: string
  centered?: boolean
}>(), {
  size: 'md',
  text: '',
  centered: false,
})

const sizeClass = computed(() => `base-spinner-${props.size}`)
</script>

<style scoped>
.base-spinner-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.base-spinner-wrap.centered {
  justify-content: center;
  padding: 40px;
}
.base-spinner {
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  flex-shrink: 0;
}
.base-spinner-sm { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.3); border-top-color: var(--accent-blue); }
.base-spinner-md { width: 20px; height: 20px; border: 2px solid var(--border-subtle); border-top-color: var(--accent-blue); }
.base-spinner-lg { width: 32px; height: 32px; border: 3px solid var(--border-subtle); border-top-color: var(--accent-blue); }
.base-spinner-text {
  font-size: 13px;
  color: var(--text-tertiary);
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
