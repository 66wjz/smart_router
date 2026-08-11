<template>
  <aside class="base-sidebar" :class="{ collapsed: isCollapsed }">
    <!-- Header -->
    <div v-if="title || $slots.header" class="sidebar-header">
      <slot name="header">
        <span v-if="title" class="sidebar-title">{{ title }}</span>
      </slot>
    </div>

    <!-- Navigation -->
    <nav class="sidebar-nav">
      <div v-for="group in visibleGroups" :key="group.label" class="nav-group">
        <div v-if="group.label && showLabels" class="nav-group-label">{{ group.label }}</div>
        <div
          v-for="item in group.items"
          :key="item.key"
          class="nav-item"
          :class="{ active: activeKey === item.key }"
          :title="isCollapsed ? item.label : ''"
          @click="$emit('select', item.key)"
        >
          <BaseIcon v-if="item.icon" :name="item.icon" :size="16" />
          <span v-if="showLabels" class="nav-item-label">{{ item.label }}</span>
        </div>
      </div>
    </nav>

    <!-- Collapse toggle at bottom -->
    <div v-if="collapsible" class="sidebar-footer">
      <button class="collapse-btn" @click="toggleCollapse" :title="isCollapsed ? '展开' : '收起'">
        <BaseIcon name="panel-left-close" :size="16"
          :style="{ transform: isCollapsed ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }" />
        <span v-if="showLabels" class="collapse-label">收起菜单</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import BaseIcon from '@/components/base/BaseIcon.vue'

export interface NavItem {
  key: string
  label: string
  icon?: string
  visible?: boolean
}

export interface NavGroup {
  label?: string
  items: NavItem[]
}

const props = withDefaults(defineProps<{
  title?: string
  activeKey: string
  groups: NavGroup[]
  collapsible?: boolean
  defaultCollapsed?: boolean
}>(), {
  title: '',
  collapsible: true,
  defaultCollapsed: false,
})

defineEmits<{
  select: [key: string]
}>()

const isCollapsed = ref(props.defaultCollapsed)

// 文字标签：收起时立即隐藏；展开时等宽度动画（0.2s）彻底走完才显示，避免跳动
const showLabels = ref(!props.defaultCollapsed)
let expandTimer: ReturnType<typeof setTimeout> | null = null

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  if (isCollapsed.value) {
    if (expandTimer) clearTimeout(expandTimer)
    showLabels.value = false
  } else {
    expandTimer = setTimeout(() => {
      showLabels.value = true
    }, 200)
  }
}

const visibleGroups = computed(() => {
  return props.groups
    .map(group => ({
      ...group,
      items: group.items.filter(item => item.visible !== false)
    }))
    .filter(group => group.items.length > 0)
})
</script>

<style scoped>
.base-sidebar {
  height: 100%;
  background: var(--bg-base);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 180px;
  overflow: hidden;
  transition: width 0.2s ease;
}

.base-sidebar.collapsed {
  width: 52px;
}

/* Header */
.sidebar-header {
  display: flex;
  align-items: center;
  padding: 16px 12px 12px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  min-height: 48px;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
}

.collapsed .sidebar-title {
  display: none;
}

/* Footer */
.sidebar-footer {
  padding: 8px 6px;
  flex-shrink: 0;
}

.collapse-btn {
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 8px 6px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: var(--control-height-sm);
  box-sizing: border-box;
  font-size: 13px;
  transition: all 0.15s;
}

.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.collapse-label {
  color: var(--text-tertiary);
}

.collapsed .collapse-btn {
  justify-content: center;
  padding: 8px 0;
}

/* Navigation */
.sidebar-nav {
  padding: 8px 0;
  flex: 1;
  overflow-y: auto;
}

.nav-group {
  padding: 4px 0;
}

.nav-group-label {
  padding: 8px 12px 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin: 0 6px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.15s;
  white-space: nowrap;
  position: relative;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-blue-muted);
  color: var(--accent-blue);
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: -6px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 18px;
  background: var(--accent-blue);
  border-radius: 0 3px 3px 0;
}

.nav-item-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.collapsed .nav-item {
  justify-content: center;
  padding: 10px 0;
  margin: 0 6px;
}

/* Scrollbar */
.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: 2px;
}

.sidebar-nav::-webkit-scrollbar-thumb:hover {
  background: var(--border-emphasis);
}
</style>
