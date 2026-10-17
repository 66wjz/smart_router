<template>
  <div>
    <!-- 一、同名模型聚合组（CH-019 二期：可视化 + 可控） -->
    <BaseSection variant="card" title="同名模型聚合（跨源自动兜底）">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="loadGroups">刷新</BaseButton>
      </template>

      <el-alert
        title="同一个模型名分布在多个上游源时，默认自动互为候选（按上游顺序兜底）。你可以勾选参与聚合的源、拖动调整优先级、或关闭某个模型的聚合。未编辑过的模型保持自动发现。"
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
      />

      <div v-if="!groups.length" class="empty-tip">
        <el-text type="info">当前没有同名多源模型（同一模型名只存在于一个上游源时不构成聚合）</el-text>
      </div>

      <div v-for="g in groups" :key="g.model" class="group-card">
        <div class="group-head">
          <div class="group-title">
            <code class="group-model">{{ g.model }}</code>
            <BaseBadge :variant="g.configured ? 'blue' : 'gray'">
              {{ g.configured ? '已手动配置' : '自动发现' }}
            </BaseBadge>
            <BaseBadge :variant="g.sources.length > 1 ? 'green' : 'amber'">
              {{ g.enabled ? `${g.sources.length} 源聚合` : '聚合已关闭' }}
            </BaseBadge>
          </div>
          <div class="group-ops">
            <span class="op-label">启用聚合</span>
            <el-switch
              :model-value="g.enabled"
              size="small"
              :disabled="savingModel === g.model"
              @change="(val: boolean | string | number) => toggleGroup(g, Boolean(val))"
            />
            <BaseButton
              v-if="g.configured"
              variant="ghost"
              size="sm"
              :disabled="savingModel === g.model"
              @click="resetGroup(g)"
            >
              恢复自动
            </BaseButton>
            <BaseButton
              variant="primary"
              size="sm"
              :disabled="savingModel === g.model"
              @click="openEdit(g)"
            >
              {{ savingModel === g.model ? '保存中…' : '编辑候选' }}
            </BaseButton>
          </div>
        </div>

        <!-- 当前生效顺序（只读展示，直观看到"怎么聚合的"） -->
        <div class="source-flow">
          <template v-for="(s, i) in g.sources" :key="s">
            <span class="source-chip" :class="{ 'is-first': i === 0 }">
              <span class="chip-index">{{ i + 1 }}</span>
              {{ s }}
              <el-text v-if="i === 0" type="success" size="small">首选</el-text>
              <el-text v-else-if="i === g.sources.length - 1" type="info" size="small">兜底</el-text>
            </span>
            <span v-if="i < g.sources.length - 1" class="arrow">→</span>
          </template>
          <span v-if="!g.sources.length" class="empty-tip"><el-text type="warning">没有任何可用源</el-text></span>
        </div>

        <div v-if="!g.enabled" class="group-warn">
          <el-text type="warning" size="small">聚合已关闭：请求该模型时只走第一个可用源，不做跨源兜底。</el-text>
        </div>
        <div v-else-if="g.auto_sources.length > g.sources.length" class="group-warn">
          <el-text type="info" size="small">
            还有 {{ g.auto_sources.length - g.sources.length }} 个源（{{ g.auto_sources.filter((x: string) => !g.sources.includes(x)).join('、') }}）未被纳入聚合。
          </el-text>
        </div>
      </div>
    </BaseSection>

    <!-- 二、聚合模型名（原有功能：手写聚合名，候选来自路由规则） -->
    <BaseSection variant="card" title="聚合模型名（手写规则聚合）" style="margin-top: 16px">
      <el-alert
        title="这里的名字是客户端请求时使用的统一模型名，候选来自「路由规则」页配置的候选列表；与上面的同名聚合是两套独立机制。"
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
      />

      <div v-if="names.length" style="margin-bottom: 16px">
        <BaseBadge v-for="n in names" :key="n" variant="default" style="margin: 4px">{{ n }}</BaseBadge>
      </div>

      <el-form label-width="120px" style="max-width: 560px">
        <el-form-item label="聚合模型名">
          <BaseInput v-model="namesText" placeholder="逗号分隔，如 smart-latest, smart-chat" />
        </el-form-item>
        <el-form-item>
          <BaseButton variant="primary" :disabled="saving" @click="handleSave">
            {{ saving ? '保存中...' : '保存' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 编辑候选弹窗：拖拽排序 + 勾选源 -->
    <BaseModal v-model:visible="editVisible" :title="`编辑聚合候选：${editModel}`" size="large">
      <el-alert
        title="拖动调整优先级（从上到下即请求尝试顺序），勾选决定哪些源参与聚合。"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <div ref="dragListRef" class="drag-list">
        <div v-for="item in editItems" :key="item.upstream" class="drag-item" :class="{ 'is-off': !item.checked }">
          <span class="drag-handle" role="button" tabindex="0" aria-label="拖动调整顺序" title="拖动调整顺序">⠿</span>
          <el-checkbox v-model="item.checked" />
          <span class="drag-name">{{ item.upstream }}</span>
          <span class="drag-upstream-name">{{ upstreamName(item.upstream) }}</span>
          <BaseBadge v-if="!item.inPool" variant="amber">该源当前无此模型</BaseBadge>
          <BaseBadge v-if="item.checked && indexOfChecked(item) === 0" variant="green">首选</BaseBadge>
          <el-input-number
            v-model="item.weight"
            :min="1"
            :max="10"
            size="small"
            style="width: 90px"
            :disabled="!item.checked"
          />
        </div>
      </div>
      <el-empty v-if="!editItems.length" description="没有可选的源" :image-size="50" />

      <template #footer>
        <BaseButton variant="ghost" @click="editVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="savingModel === editModel" @click="saveEdit">
          {{ savingModel === editModel ? '保存中…' : '保存' }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import { getAggregatedNames, saveAggregatedNames } from '@/api/aggregated'
import { deleteModelGroup, listModelGroups, saveModelGroup } from '@/api/model_groups'
import { listUpstreams } from '@/api/upstreams'
import { reloadConfig } from '@/api/common'

// ---------- 原有：聚合模型名 ----------
const names = ref<string[]>([])
const namesText = ref('')
const saving = ref(false)

// ---------- 新增：同名聚合组 ----------
const groups = ref<any[]>([])
const upstreams = ref<any[]>([])
const savingModel = ref('')

const editVisible = ref(false)
const editModel = ref('')
const editItems = ref<{ upstream: string; checked: boolean; weight: number; inPool: boolean }[]>([])
const dragListRef = ref<HTMLElement | null>(null)
let sortable: Sortable | null = null

function upstreamName(id: string): string {
  return upstreams.value.find((u) => u.id === id)?.name || ''
}

function indexOfChecked(item: { upstream: string; checked: boolean }): number {
  return editItems.value.filter((x) => x.checked).findIndex((x) => x.upstream === item.upstream)
}

async function loadGroups() {
  const res: any = await listModelGroups()
  groups.value = res.groups || []
}

async function loadUpstreams() {
  const res: any = await listUpstreams()
  upstreams.value = res.upstreams || []
}

async function toggleGroup(g: any, enabled: boolean) {
  savingModel.value = g.model
  try {
    await saveModelGroup(g.model, g.sources.map((s: string) => ({ upstream: s, weight: 1 })), enabled)
    g.enabled = enabled
    ElMessage.success(enabled ? `「${g.model}」已启用跨源聚合` : `「${g.model}」已关闭聚合（仅走首选源）`)
    await reloadConfig()
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingModel.value = ''
  }
}

async function resetGroup(g: any) {
  await ElMessageBox.confirm(`确定对「${g.model}」恢复自动发现吗？手动配置将被删除。`, '恢复自动', { type: 'warning' })
  savingModel.value = g.model
  try {
    await deleteModelGroup(g.model)
    ElMessage.success('已恢复自动发现')
    await reloadConfig()
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    savingModel.value = ''
  }
}

function openEdit(g: any) {
  editModel.value = g.model
  // 候选池 = 自动发现 ∪ 当前配置（保证已配置但当前不可用的源也能看到并取消）
  const pool = Array.from(new Set([...g.auto_sources, ...g.sources]))
  editItems.value = pool.map((uid: string) => ({
    upstream: uid,
    checked: g.sources.includes(uid),
    weight: 1,
    inPool: g.auto_sources.includes(uid),
  }))
  // 已勾选的按原顺序排前面，未勾选的后置
  editItems.value.sort((a, b) => {
    const ai = a.checked ? g.sources.indexOf(a.upstream) : 999
    const bi = b.checked ? g.sources.indexOf(b.upstream) : 999
    return ai - bi
  })
  editVisible.value = true
  nextTick(initSortable)
}

function initSortable() {
  if (!dragListRef.value) return
  sortable?.destroy()
  sortable = Sortable.create(dragListRef.value, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'drag-ghost',
    onEnd: (evt) => {
      const from = evt.oldIndex ?? -1
      const to = evt.newIndex ?? -1
      if (from < 0 || to < 0 || from === to) return
      const moved = editItems.value.splice(from, 1)[0]
      editItems.value.splice(to, 0, moved)
    },
  })
}

async function saveEdit() {
  const picked = editItems.value.filter((x) => x.checked)
  if (!picked.length) {
    ElMessage.warning('至少勾选一个上游源')
    return
  }
  savingModel.value = editModel.value
  try {
    await saveModelGroup(
      editModel.value,
      picked.map((x) => ({ upstream: x.upstream, weight: x.weight })),
      true,
    )
    ElMessage.success('聚合配置已保存')
    editVisible.value = false
    await reloadConfig()
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingModel.value = ''
  }
}

// ---------- 原有：聚合名 ----------
async function loadNames() {
  const res: any = await getAggregatedNames()
  names.value = res.names || []
  namesText.value = (res.names || []).join(', ')
}

async function handleSave() {
  const newNames = namesText.value
    .split(',')
    .map((n) => n.trim())
    .filter(Boolean)
  saving.value = true
  try {
    await saveAggregatedNames(newNames)
    ElMessage.success('聚合模型名已更新')
    await reloadConfig()
    loadNames()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadNames(), loadUpstreams()])
  await loadGroups()
})
</script>

<style scoped>
.empty-tip {
  padding: 8px 0;
}
.group-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 12px;
  background: var(--bg-base);
}
.group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.group-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.95rem;
  font-weight: 600;
}
.group-ops {
  display: flex;
  align-items: center;
  gap: 8px;
}
.op-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}
.source-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.source-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-hover);
  font-size: 0.8rem;
}
.source-chip.is-first {
  background: var(--accent-green-muted, rgba(103, 194, 58, 0.12));
}
.chip-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-base);
  font-size: 0.7rem;
}
.arrow {
  color: var(--text-tertiary);
  font-size: 0.85rem;
}
.group-warn {
  margin-top: 8px;
}
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
.drag-item.is-off {
  opacity: 0.55;
}
.drag-handle {
  cursor: grab;
  color: var(--text-tertiary);
  font-size: 1rem;
  user-select: none;
}
.drag-name {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  min-width: 120px;
}
.drag-upstream-name {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  flex: 1;
}
.drag-ghost {
  opacity: 0.4;
}
</style>
