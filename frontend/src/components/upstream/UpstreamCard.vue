<template>
  <div class="upstream-card" :class="{ 'is-disabled': !u.enabled }">
    <div class="upstream-header">
      <div class="upstream-title">
        <span class="upstream-name">{{ u.name }}</span>
        <BaseBadge variant="gray">{{ u.format }}</BaseBadge>
        <BaseBadge v-if="u.smart_retry" variant="blue">智能重试</BaseBadge>
        <BaseBadge v-for="g in groupList" :key="g" variant="green">{{ g }}</BaseBadge>
        <BaseBadge :variant="u.enabled ? 'green' : 'gray'">{{ u.enabled ? '已启用' : '已禁用' }}</BaseBadge>
      </div>
      <div class="upstream-actions">
        <el-switch
          :model-value="u.enabled"
          :loading="toggling"
          active-text="启用"
          inactive-text="禁用"
          @change="(val: boolean | string | number) => $emit('toggle', Boolean(val))"
        />
        <BaseButton variant="ghost" size="sm" @click="$emit('edit')">修改</BaseButton>
        <BaseButton variant="danger" size="sm" @click="$emit('delete')">删除</BaseButton>
      </div>
    </div>

    <div class="upstream-meta">
      ID: <span class="meta-val">{{ u.id }}</span> &nbsp;·&nbsp;
      Base URL: <span class="meta-val">{{ u.base_url }}</span> &nbsp;·&nbsp;
      <span class="meta-val">{{ u.key_count }} 个 Key</span>
      <template v-if="u.key_count > 1">
        &nbsp;·&nbsp; 首 Key: <span class="meta-val">{{ u.api_key }}</span>
      </template>
    </div>

    <ModelList :u="u" />

    <FetchModelsPanel v-if="models.fetchPanelOpen[u.id]" :u="u" />
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import ModelList from './ModelList.vue'
import FetchModelsPanel from './FetchModelsPanel.vue'
import { UPSTREAM_MODELS_KEY, type UpstreamModels } from '@/composables/useUpstreamModels'

const props = defineProps<{
  u: any
  toggling: boolean
}>()

defineEmits<{
  toggle: [enabled: boolean]
  edit: []
  delete: []
}>()

const models = inject<UpstreamModels>(UPSTREAM_MODELS_KEY)!

const groupList = computed<string[]>(() =>
  props.u.groups && props.u.groups.length ? props.u.groups : [props.u.group],
)
</script>

<style scoped>
.upstream-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--bg-base);
}
.upstream-card.is-disabled {
  opacity: 0.55;
  background: var(--bg-elevated);
}
.upstream-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 12px;
  flex-wrap: wrap;
}
.upstream-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.upstream-name {
  font-weight: 600;
  font-size: 1.05rem;
}
.upstream-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.upstream-meta {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.meta-val {
  color: var(--text-tertiary);
}
</style>
