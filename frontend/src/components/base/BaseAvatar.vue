<template>
  <div :class="avatarClass">
    {{ displayChar }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  name?: string
  size?: 'sm' | 'md' | 'lg'
  color?: 'blue' | 'purple' | 'green' | 'amber' | 'red'
}>(), {
  name: '',
  size: 'md',
  color: 'blue',
})

const displayChar = computed(() => props.name ? props.name[0] : '?')

const avatarClass = computed(() => [
  'base-avatar',
  `base-avatar-${props.size}`,
  `base-avatar-${props.color}`,
])
</script>

<style scoped>
.base-avatar {
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex-shrink: 0;
}
.base-avatar-sm { width: 28px; height: 28px; font-size: 12px; }
.base-avatar-md { width: 36px; height: 36px; font-size: 14px; }
.base-avatar-lg { width: 48px; height: 48px; font-size: 18px; }
.base-avatar-blue { background: var(--accent-blue-muted); color: var(--accent-blue); }
.base-avatar-purple { background: var(--accent-purple-muted); color: var(--accent-purple); }
.base-avatar-green { background: var(--accent-green-muted); color: var(--accent-green); }
.base-avatar-amber { background: var(--accent-amber-muted); color: var(--accent-amber); }
.base-avatar-red { background: var(--accent-red-muted); color: var(--accent-red); }
</style>
