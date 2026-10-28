<template>
  <div>
    <BaseNotice text="权重决定请求分发比例（A=2、B=1、C=1 → 50%/25%/25%）；成员连续失败进入冷却后，其余成员按剩余权重自动重新分配。从上到下只决定失败时的兜底顺序。每个成员可指定该源里的真实模型名，因此不同源的异名模型也能聚合到一起。" />

    <div ref="dragListRef" class="drag-list">
      <div v-for="item in items" :key="item.upstream + '|' + item.model" class="drag-item">
        <span class="drag-handle" role="button" tabindex="0" aria-label="拖动调整顺序" title="拖动调整顺序">⠿</span>
        <span class="drag-upstream">{{ item.upstream }}</span>
        <el-select :model-value="item.model" filterable allow-create default-first-option size="small"
          class="drag-model-select" placeholder="该源里的真实模型名"
          @update:model-value="(v: string) => onModelChange(item, v)">
          <el-option v-for="m in modelsOf(item.upstream)" :key="m" :label="m" :value="m" />
        </el-select>
        <el-input-number :model-value="item.weight" :min="1" :max="10" size="small" style="width: 90px"
          @update:model-value="(v: number | undefined) => onWeightChange(item, v)" />
        <BaseButton variant="danger" size="sm" @click="$emit('remove', item)">移除</BaseButton>
      </div>
    </div>
    <BaseEmptyState v-if="!items.length" description="还没有成员，请在下方添加" />

    <div class="add-row">
      <el-select v-model="addUpstream" placeholder="选择上游源" size="small" style="width: 200px"
        @change="onAddUpstreamChange">
        <el-option v-for="u in upstreams" :key="u.id" :label="u.name || u.id" :value="u.id" />
      </el-select>
      <el-select v-model="addModel" filterable allow-create default-first-option size="small"
        placeholder="选择/输入真实模型名" style="width: 300px">
        <el-option v-for="m in modelsOf(addUpstream)" :key="m" :label="m" :value="m" />
      </el-select>
      <BaseButton variant="primary" size="sm" @click="addItem">+ 添加成员</BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import Sortable from 'sortablejs'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'

export interface MemberItem {
  upstream: string
  model: string
  weight: number
}

const props = defineProps<{
  items: MemberItem[]
  upstreams: { id: string; name?: string }[]
  /** 上游 → 该源可用真实模型名 */
  sourceModels: Record<string, string[]>
}>()

const emit = defineEmits<{
  'update:items': [items: MemberItem[]]
  'ensure-models': [upstream: string]
  remove: [item: MemberItem]
}>()

const dragListRef = ref<HTMLElement | null>(null)
const addUpstream = ref(props.upstreams[0]?.id || '')
const addModel = ref('')
let sortable: Sortable | null = null

function modelsOf(upstream: string): string[] {
  return props.sourceModels[upstream] || []
}

function patch(index: number, patchObj: Partial<MemberItem>) {
  const next = props.items.map((it, i) => (i === index ? { ...it, ...patchObj } : it))
  emit('update:items', next)
}

function onModelChange(item: MemberItem, value: string) {
  const i = props.items.indexOf(item)
  if (i >= 0) patch(i, { model: value })
}

function onWeightChange(item: MemberItem, value: number | undefined) {
  const i = props.items.indexOf(item)
  if (i >= 0) patch(i, { weight: Number(value) || 1 })
}

function onAddUpstreamChange() {
  addModel.value = ''
  emit('ensure-models', addUpstream.value)
}

function addItem() {
  if (!addUpstream.value || !addModel.value) {
    ElMessage.warning('请选择上游源并填写模型名')
    return
  }
  const dup = props.items.some((x) => x.upstream === addUpstream.value && x.model === addModel.value)
  if (dup) {
    ElMessage.info('该成员已存在')
    return
  }
  emit('update:items', [...props.items, { upstream: addUpstream.value, model: addModel.value, weight: 1 }])
  addModel.value = ''
}

function initSortable() {
  if (!dragListRef.value) return
  sortable?.destroy()
  sortable = Sortable.create(dragListRef.value, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'drag-ghost',
    fallbackTolerance: 3,
    group: { name: 'agg-members', pull: false, put: false },
    onEnd: (evt) => {
      const from = evt.oldIndex ?? -1
      const to = evt.newIndex ?? -1
      if (from < 0 || to < 0 || from === to) return
      const next = [...props.items]
      const moved = next.splice(from, 1)[0]
      next.splice(to, 0, moved)
      emit('update:items', next)
    },
  })
}

watch(() => props.upstreams.length, () => {
  if (!addUpstream.value && props.upstreams.length) addUpstream.value = props.upstreams[0].id
}, { immediate: true })

// 拖拽列表挂载后初始化（弹窗打开时才渲染）
watch(dragListRef, (el) => {
  if (el) nextTick(initSortable)
})

onBeforeUnmount(() => {
  sortable?.destroy()
  sortable = null
})
</script>

<style scoped>
.drag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.drag-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-base);
}
.drag-handle {
  cursor: grab;
  color: var(--text-tertiary);
  font-size: 1rem;
  user-select: none;
}
.drag-upstream {
  font-size: 0.82rem;
  color: var(--text-secondary, var(--text-tertiary));
  min-width: 110px;
}
.drag-model-select {
  flex: 1;
  min-width: 240px;
}
.drag-ghost {
  opacity: 0.35;
  background: var(--accent-blue-muted, rgba(64, 158, 255, 0.12)) !important;
  border: 1px dashed var(--accent-blue) !important;
}
.drag-item.sortable-chosen {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
}
.drag-item.sortable-ghost {
  border-top: 2px solid var(--accent-blue) !important;
}
.add-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
</style>
