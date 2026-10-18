<template>
  <div class="model-section">
    <div class="model-head">
      <div class="model-title">
        已配置模型
        <span class="model-count">（{{ list.length }} 个）</span>
      </div>
      <div class="model-ops">
        <BaseButton variant="primary" size="sm"
          :disabled="models.testingAll[u.id] || !list.length"
          @click="models.testAllModels(u)">
          {{ models.testingAll[u.id] ? `测试中 ${models.testProgress[u.id] || ''}` : '全量测试' }}
        </BaseButton>
        <BaseButton variant="ghost" size="sm" @click="models.openFetchPanel(u)">
          {{ models.fetchPanelOpen[u.id] ? '收起面板' : '拉取模型' }}
        </BaseButton>
        <BaseButton variant="ghost" size="sm" @click="$emit('manual-add')">手动添加</BaseButton>
      </div>
    </div>

    <div v-if="list.length" class="model-list" :data-sortable-upstream="u.id">
      <div class="model-batch-bar">
        <el-checkbox :model-value="models.allSelected(u)" @change="models.toggleSelectAllModels(u)">全选</el-checkbox>
        <span class="batch-count">已选 {{ models.selectedModelCount(u) }} 个</span>
        <div class="batch-ops">
          <BaseButton variant="danger" size="sm"
            :disabled="!models.selectedModelCount(u) || models.testingAll[u.id]"
            @click="models.batchDelete(u)">批量删除</BaseButton>
          <BaseButton variant="primary" size="sm"
            :disabled="!models.selectedModelCount(u) || models.testingAll[u.id]"
            @click="models.batchTest(u)">批量测试</BaseButton>
        </div>
      </div>

      <div
        v-for="m in models.visibleModels(u)"
        :key="m.name"
        class="model-row"
        :class="{ 'model-disabled': m.enabled === false }"
        :data-model="m.name"
      >
        <span
          class="drag-handle"
          role="button"
          tabindex="0"
          aria-label="拖动调整模型顺序"
          :class="{ 'is-disabled': collapsed && !models.modelExpanded[u.id] }"
          :title="collapsed && !models.modelExpanded[u.id] ? '展开全部后可拖拽排序' : '拖动调整顺序'"
        >⠿</span>
        <el-checkbox v-model="models.modelSelected[u.id][m.name]" :disabled="models.testingAll[u.id]" />
        <code class="model-name">{{ m.name }}</code>
        <el-tag v-if="m.enabled === false" type="info" size="small">已禁用</el-tag>
        <el-select
          :model-value="m.protocol || 'inherit'"
          size="small"
          style="width: 160px"
          :disabled="models.testingAll[u.id]"
          @change="(val: string) => models.setModelProtocol(u, m.name, val)"
        >
          <el-option :label="`继承（${u.format}）`" value="inherit" />
          <el-option label="openai" value="openai" />
          <el-option label="anthropic" value="anthropic" />
          <el-option label="responses" value="responses" />
        </el-select>
        <span class="model-status">
          <BaseBadge :variant="models.modelStateBadge(u, m.name)">{{ models.modelStateText(u, m.name) }}</BaseBadge>
          <span v-if="models.modelStateDetail(u, m.name)" class="model-detail"
            :class="{ 'detail-fail': models.modelState(u, m.name)?.status === 'fail' }">
            {{ models.modelStateDetail(u, m.name) }}
          </span>
        </span>
        <BaseButton variant="primary" size="sm"
          :disabled="models.isTesting(u, m.name) || models.testingAll[u.id]"
          @click="models.testModel(u, m.name)">
          {{ models.isTesting(u, m.name) ? '测试中...' : (models.modelState(u, m.name)?.status === 'ok' ? '再测' : '测试') }}
        </BaseButton>
        <BaseButton variant="danger" size="sm" :disabled="models.testingAll[u.id]"
          @click="models.removeModel(u, m.name)">删除</BaseButton>
        <div class="model-row-right">
          <el-switch
            :model-value="m.enabled !== false"
            size="small"
            :disabled="models.testingAll[u.id] || models.togglingModels[`${u.id}:${m.name}`]"
            @change="(val: boolean | string | number) => models.handleToggleModel(u, m.name, Boolean(val))"
          />
        </div>
      </div>

      <div v-if="collapsed" class="model-expand-bar">
        <BaseButton variant="ghost" size="sm" @click="models.toggleExpand(u)">
          {{ models.modelExpanded[u.id] ? '收起模型列表' : `展开全部（${list.length} 个）` }}
        </BaseButton>
      </div>
    </div>
    <div v-else class="model-empty">
      暂无已配置模型，可点击「拉取模型」批量加入或「手动添加」
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { COLLAPSE_THRESHOLD, UPSTREAM_MODELS_KEY, type UpstreamModels } from '@/composables/useUpstreamModels'

const props = defineProps<{
  u: { id: string; name: string; format?: string }
}>()

defineEmits<{
  'manual-add': []
}>()

const models = inject<UpstreamModels>(UPSTREAM_MODELS_KEY)!

const list = computed(() => models.modelsByUpstream[props.u.id] || [])
const collapsed = computed(() => list.value.length > COLLAPSE_THRESHOLD)
</script>

<style scoped>
.model-section {
  margin-top: 12px;
  padding: 10px;
  background: var(--bg-base);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}
.model-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.model-title {
  font-weight: 600;
  font-size: 0.9rem;
}
.model-count {
  font-weight: 400;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-left: 4px;
}
.model-ops {
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-list {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}
.model-batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 10px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-subtle);
}
.batch-count {
  font-size: 0.8rem;
  color: var(--text-secondary);
}
.batch-ops {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.model-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-base);
}
.model-row + .model-row {
  border-top: 1px solid var(--border-subtle);
}
.model-row:hover {
  background: var(--bg-hover);
}
.model-row.model-disabled .model-name {
  color: var(--text-tertiary);
  text-decoration: line-through;
}
.model-row-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.drag-handle {
  cursor: grab;
  color: var(--text-tertiary);
  font-size: 1rem;
  user-select: none;
  flex-shrink: 0;
}
.drag-handle:active {
  cursor: grabbing;
}
.drag-handle.is-disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.drag-ghost {
  opacity: 0.35;
  background: var(--accent-blue-muted, rgba(64, 158, 255, 0.12)) !important;
  border: 1px dashed var(--accent-blue) !important;
}
.model-row.sortable-chosen {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
}
.model-row.sortable-ghost {
  border-top: 2px solid var(--accent-blue) !important;
}
.model-name {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.model-detail {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-detail.detail-fail {
  color: var(--accent-red);
  max-width: 300px;
  white-space: normal;
  overflow: visible;
  line-height: 1.5;
}
.model-expand-bar {
  display: flex;
  justify-content: center;
  padding: 6px 0;
  border-top: 1px solid var(--border-subtle);
}
.model-empty {
  padding: 8px 4px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
}
</style>
