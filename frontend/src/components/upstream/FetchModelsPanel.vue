<template>
  <div class="fetch-panel">
    <div class="fetch-bar">
      <span class="fetch-title">拉取结果（共 {{ remoteCount }} 个）</span>
      <BaseInput
        :model-value="models.fetchSearch[u.id] || ''"
        size="sm"
        placeholder="搜索模型名…"
        style="width: 220px"
        @update:model-value="(v: string) => models.fetchSearch[u.id] = v"
      />
      <BaseButton variant="ghost" size="sm" @click="models.toggleSelectAll(u)">全选</BaseButton>
    </div>
    <div class="fetch-chips">
      <BaseCheckTag
        v-for="m in models.filteredRemoteModels(u)"
        :key="m"
        v-model="models.remoteChecked[u.id][m]"
        size="sm"
      >
        {{ m }}
      </BaseCheckTag>
    </div>
    <div class="fetch-foot">
      <span class="fetch-count">已选 {{ models.selectedRemoteCount(u) }} 个</span>
      <BaseButton variant="primary" size="sm" :disabled="models.selectedRemoteCount(u) === 0"
        @click="models.handleJoin(u)">
        加入模型列表
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseCheckTag from '@/components/base/BaseCheckTag.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { UPSTREAM_MODELS_KEY, type UpstreamModels } from '@/composables/useUpstreamModels'

const props = defineProps<{
  u: { id: string }
}>()

const models = inject<UpstreamModels>(UPSTREAM_MODELS_KEY)!

const remoteCount = computed(() => (models.remoteModelsByUpstream[props.u.id] || []).length)
</script>

<style scoped>
.fetch-panel {
  margin-top: 8px;
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-elevated);
}
.fetch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.fetch-title {
  font-weight: 600;
  font-size: 0.85rem;
}
.fetch-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 140px;
  overflow-y: auto;
}
.fetch-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}
.fetch-count {
  font-size: 0.8rem;
  color: var(--text-secondary);
}
</style>
