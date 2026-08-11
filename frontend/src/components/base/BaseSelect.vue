<template>
  <div class="custom-select-wrapper" ref="wrapperRef">
    <div
      class="custom-select-trigger"
      :class="{ open: isOpen, 'size-sm': size === 'sm' }"
      @click.stop="isOpen = !isOpen"
    >
      <span class="custom-select-value">
        {{ selectedLabel || placeholder }}
      </span>
      <BaseIcon name="chevron-down" :size="12" />
    </div>
    <Transition name="dropdown">
      <Teleport to="body">
        <div
          v-if="isOpen"
          class="custom-select-dropdown"
          :style="dropdownStyle"
          @click.stop
        >
          <label
            v-for="option in options"
            :key="option.value"
            class="custom-select-option"
            :class="{ selected: isSelected(option) }"
            @click="selectOption(option)"
          >
            <span class="custom-select-option-label">{{ option.label }}</span>
            <BaseIcon v-if="isSelected(option)" name="check" :size="14" />
          </label>
        </div>
      </Teleport>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import BaseIcon from './BaseIcon.vue'

interface Option {
  value: string | number
  label: string
}

type SelectValue = string | number | (string | number)[] | undefined

const props = defineProps<{
  modelValue: SelectValue
  options: Option[]
  placeholder?: string
  size?: 'default' | 'sm'
  multiple?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string | number | (string | number)[]]
}>()

const isOpen = ref(false)
const wrapperRef = ref<HTMLElement | null>(null)

const selectedLabel = computed(() => {
  if (props.multiple) {
    const arr = Array.isArray(props.modelValue) ? props.modelValue : []
    return arr.length > 0 ? `已选 ${arr.length} 项` : ''
  }
  const option = props.options.find(o => o.value === props.modelValue)
  return option?.label || ''
})

function isSelected(option: Option): boolean {
  if (props.multiple) {
    return Array.isArray(props.modelValue) && props.modelValue.includes(option.value)
  }
  return props.modelValue === option.value
}

const dropdownStyle = computed(() => {
  if (!wrapperRef.value || !isOpen.value) return {}
  const rect = wrapperRef.value.getBoundingClientRect()
  const maxHeight = Math.min(240, window.innerHeight - rect.bottom - 16)
  return {
    left: `${rect.left}px`,
    top: `${rect.top + rect.height + 4}px`,
    width: `${rect.width}px`,
    maxHeight: `${maxHeight}px`,
  }
})

function selectOption(option: Option) {
  if (props.multiple) {
    const arr = Array.isArray(props.modelValue) ? [...props.modelValue] : []
    const idx = arr.indexOf(option.value)
    if (idx === -1) {
      arr.push(option.value)
    } else {
      arr.splice(idx, 1)
    }
    emit('update:modelValue', arr)
    return
  }
  emit('update:modelValue', option.value)
  isOpen.value = false
}

function handleClickOutside(e: MouseEvent) {
  if (wrapperRef.value && !wrapperRef.value.contains(e.target as Node)) {
    isOpen.value = false
  }
}

watch(() => props.modelValue, () => {
  if (!props.multiple) {
    isOpen.value = false
  }
})

watch(isOpen, (newVal) => {
  if (newVal) {
    document.addEventListener('click', handleClickOutside)
  } else {
    document.removeEventListener('click', handleClickOutside)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.custom-select-wrapper {
  position: relative;
  display: inline-block;
}

.custom-select-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-base);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  height: var(--control-height);
  cursor: pointer;
  transition: all var(--duration-fast);
  min-width: 120px;
  font-size: 13px;
  user-select: none;
}

.custom-select-trigger:hover {
  border-color: var(--border-emphasis);
}

.custom-select-trigger.size-sm {
  padding: 0 8px;
  font-size: 13px;
  min-width: 100px;
  height: var(--control-height-sm);
  box-sizing: border-box;
}

.custom-select-trigger.open {
  border-color: var(--accent-blue);
}

.custom-select-value {
  flex: 1;
  text-align: left;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-select-trigger:not(.open) .custom-select-value {
  color: var(--text-tertiary);
}

.custom-select-trigger.open .custom-select-value {
  color: var(--text-primary);
}

.custom-select-trigger svg {
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: transform var(--duration-fast);
}

.custom-select-trigger.open svg {
  transform: rotate(180deg);
}

.custom-select-dropdown {
  position: fixed;
  z-index: var(--z-select-dropdown);
  max-height: 240px;
  overflow-y: auto;
  background: var(--bg-base);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 4px;
  box-sizing: border-box;
}

.custom-select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
  transition: background var(--duration-fast);
}

.custom-select-option-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-select-option:hover {
  background: var(--bg-hover);
}

.custom-select-option.selected {
  background: var(--accent-blue-muted);
  color: var(--accent-blue);
}

.custom-select-option svg {
  flex-shrink: 0;
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: all var(--duration-fast);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
