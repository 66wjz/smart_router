<template>
  <!-- CH-043：外壳统一走 EntityCard，内部模型列表（可操作行）原样保留 -->
  <EntityCard
    :disabled="!u.enabled"
    :selectable="selectable"
    :checked="checked"
    @update:checked="(v: boolean) => $emit('update:checked', v)"
  >
    <template #title>
      <span class="upstream-name">{{ u.name }}</span>
      <BaseBadge variant="gray">{{ u.format }}</BaseBadge>
      <BaseBadge v-if="u.smart_retry" variant="blue">智能重试</BaseBadge>
      <BaseBadge v-for="g in groupList" :key="g" variant="green">{{ g }}</BaseBadge>
      <BaseBadge :variant="u.enabled ? 'green' : 'gray'">{{ u.enabled ? '已启用' : '已禁用' }}</BaseBadge>
    </template>

    <template #actions>
      <el-switch
        :model-value="u.enabled"
        :loading="toggling"
        active-text="启用"
        inactive-text="禁用"
        @change="(val: boolean | string | number) => $emit('toggle', Boolean(val))"
      />
      <BaseButton variant="ghost" size="sm" @click="$emit('edit')">修改</BaseButton>
      <BaseButton variant="danger" size="sm" @click="$emit('delete')">删除</BaseButton>
    </template>

    <template #meta>
      ID: <span class="meta-val">{{ u.id }}</span> &nbsp;·&nbsp;
      Base URL: <span class="meta-val">{{ u.base_url }}</span> &nbsp;·&nbsp;
      <span class="meta-val">{{ u.key_count }} 个 Key</span>
      <template v-if="u.key_count > 1">
        &nbsp;·&nbsp; 首 Key: <span class="meta-val">{{ u.api_key }}</span>
      </template>
    </template>

    <ModelList :u="u" />
    <FetchModelsPanel v-if="models.fetchPanelOpen[u.id]" :u="u" />
  </EntityCard>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import EntityCard from '@/components/base/EntityCard.vue'
import ModelList from './ModelList.vue'
import FetchModelsPanel from './FetchModelsPanel.vue'
import { UPSTREAM_MODELS_KEY, type UpstreamModels } from '@/composables/useUpstreamModels'

const props = defineProps<{
  u: any
  toggling: boolean
  /** 列表页统一管理的勾选态（CH-045） */
  selectable?: boolean
  checked?: boolean
}>()

defineEmits<{
  toggle: [enabled: boolean]
  edit: []
  delete: []
  'update:checked': [value: boolean]
}>()

const models = inject<UpstreamModels>(UPSTREAM_MODELS_KEY)!

const groupList = computed<string[]>(() =>
  props.u.groups && props.u.groups.length ? props.u.groups : [props.u.group],
)
</script>

<style scoped>
/* CH-043：外壳样式由 EntityCard 统一，这里只保留本组件独有的部分 */
.upstream-name {
  font-weight: 600;
  font-size: 1.05rem;
}
.meta-val {
  color: var(--text-tertiary);
}
</style>
