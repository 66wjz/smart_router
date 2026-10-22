<template>
  <div>
    <!--
      CH-045：上游源列表与聚合模型统一走 ListPage
      （标题 + 右上操作 → 常驻工具条 + 全选 → 卡片条目 → 底部统一分页）
    -->
    <ListPage
      title="上游源列表"
      :loading="loading"
      :page="page"
      :page-size="pageSize"
      :total="filtered.length"
      :page-sizes="[10, 20, 50]"
      @update:page="page = $event"
      @update:page-size="pageSize = $event"
    >
      <template #actions>
        <BaseButton variant="primary" size="sm" @click="openAdd">+ 添加上游源</BaseButton>
      </template>

      <template #filters>
        <FilterBar :loading="loading" @search="applyFilter" @reset="resetFilter">
          <FilterField label="名称 / ID / URL" :width="280">
            <BaseInput
              v-model="filters.keyword"
              size="sm"
              placeholder="输入关键字搜索"
              @keydown.enter="applyFilter"
            />
          </FilterField>
          <FilterField label="分组" :width="160">
            <el-select v-model="filters.group" size="small" clearable placeholder="全部分组">
              <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
            </el-select>
          </FilterField>
          <FilterField label="状态" :width="130">
            <el-select v-model="filters.enabled" size="small" clearable placeholder="全部">
              <el-option label="启用" :value="true" />
              <el-option label="禁用" :value="false" />
            </el-select>
          </FilterField>
        </FilterBar>
      </template>

      <template #toolbar>
        <ListToolbar
          :count="selected.length"
          :total="filtered.length"
          :summary="`已启用 ${enabledCount} 个`"
          :actions="batchActions"
          selectable
          :all-checked="allPageChecked"
          :indeterminate="pageIndeterminate"
          @toggle-all="toggleAllOnPage"
          @clear="clearSelection"
        />
      </template>

      <BaseEmptyState v-if="!filtered.length && !loading" description="暂无上游源，请点击上方按钮添加" />

      <div v-else class="up-list">
        <UpstreamCard
          v-for="u in paged"
          :key="u.id"
          :u="u"
          :toggling="togglingIds.includes(u.id)"
          selectable
          :checked="selected.includes(u.id)"
          @update:checked="(v: boolean) => toggleChecked(u.id, v)"
          @toggle="(v: boolean) => handleToggle(u, v)"
          @edit="openEdit(u)"
          @delete="handleDelete(u)"
          @manual-add="openManualModal(u)"
        />
      </div>
    </ListPage>

    <!-- 新增 / 修改上游源（共用表单） -->
    <UpstreamFormModal
      v-model:visible="formVisible"
      :mode="formMode"
      :form="form"
      :key-text="keyText"
      :group-options="groupOptions"
      :saving="formSaving"
      @update:form="Object.assign(form, $event)"
      @update:key-text="keyText = $event"
      @save="saveForm"
    />

    <!-- 手动添加模型弹窗 -->
    <BaseModal v-model:visible="manualModal.visible" title="手动添加模型" size="wide">
      <el-form :model="manualModal" label-width="90px">
        <el-form-item label="模型名" required>
          <BaseInput v-model="manualModal.input" placeholder="多个模型名用逗号分隔，如: gpt-4o, claude-3-5-sonnet" />
          <BaseHint text="已存在的模型名会自动跳过，不会重复添加" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter :loading="manualModal.saving" confirm-text="添加" loading-text="添加中..."
          @cancel="manualModal.visible = false" @confirm="confirmManualAdd" />
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import ListToolbar from '@/components/list/ListToolbar.vue'
import FilterBar from '@/components/list/FilterBar.vue'
import FilterField from '@/components/list/FilterField.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import UpstreamCard from '@/components/upstream/UpstreamCard.vue'
import UpstreamFormModal from '@/components/upstream/UpstreamFormModal.vue'
import { emptyForm, parseKeys, type UpstreamForm } from '@/components/upstream/form'
import { UPSTREAM_MODELS_KEY, useUpstreamModels } from '@/composables/useUpstreamModels'
import {
  addUpstream, deleteUpstream, listUpstreams, updateUpstream,
} from '@/api/upstreams'
import { reloadConfig } from '@/api/common'
import { listGroups } from '@/api/groups'

const upstreams = ref<any[]>([])
const loading = ref(false)
const groupOptions = ref<{ name: string; description: string }[]>([])
const togglingIds = ref<string[]>([])

// ---------- 筛选（CH-047：与 API Key 页对齐） ----------
const filters = reactive({ keyword: '', group: '', enabled: '' as '' | boolean })
const applied = reactive({ keyword: '', group: '', enabled: '' as '' | boolean })

const filtered = computed(() => {
  return upstreams.value.filter((u) => {
    if (applied.keyword) {
      const k = applied.keyword.toLowerCase()
      const hit = String(u.name || '').toLowerCase().includes(k)
        || String(u.id || '').toLowerCase().includes(k)
        || String(u.base_url || '').toLowerCase().includes(k)
      if (!hit) return false
    }
    if (applied.group) {
      const gs: string[] = u.groups && u.groups.length ? u.groups : [u.group || 'free']
      if (!gs.includes(applied.group)) return false
    }
    if (applied.enabled !== '' && Boolean(u.enabled) !== applied.enabled) return false
    return true
  })
})

function applyFilter() {
  applied.keyword = filters.keyword.trim()
  applied.group = filters.group
  applied.enabled = filters.enabled
  page.value = 1
}

function resetFilter() {
  filters.keyword = ''
  filters.group = ''
  filters.enabled = ''
  applyFilter()
}

const page = ref(1)
const pageSize = ref(10)
const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})
const enabledCount = computed(() => upstreams.value.filter((u) => u.enabled).length)

// ---------- 多选（CH-045） ----------
/** 选中按 upstream_id 存，跨页保持 */
const selected = ref<string[]>([])

function toggleChecked(id: string, checked: boolean) {
  if (checked) {
    if (!selected.value.includes(id)) selected.value.push(id)
  } else {
    selected.value = selected.value.filter((x) => x !== id)
  }
}

function clearSelection() {
  selected.value = []
}

const pageIds = computed(() => paged.value.map((u) => u.id))
const allPageChecked = computed(() =>
  pageIds.value.length > 0 && pageIds.value.every((id) => selected.value.includes(id)),
)
const pageIndeterminate = computed(() => {
  const hit = pageIds.value.filter((id) => selected.value.includes(id)).length
  return hit > 0 && hit < pageIds.value.length
})

function toggleAllOnPage(checked: boolean) {
  if (checked) {
    selected.value = [...new Set([...selected.value, ...pageIds.value])]
  } else {
    const drop = new Set(pageIds.value)
    selected.value = selected.value.filter((id) => !drop.has(id))
  }
}

/** 批量启用/禁用：操作后保留选中 */
async function batchToggle(enabled: boolean) {
  const ids = [...selected.value]
  if (!ids.length) return
  const verb = enabled ? '启用' : '禁用'
  try {
    for (const id of ids) {
      await updateUpstream(id, { enabled })
    }
    ElMessage.success(`已${verb} ${ids.length} 个上游源`)
    await reloadConfig()
    await load()
    if ((page.value - 1) * pageSize.value >= filtered.value.length) page.value = 1
    const alive = new Set(upstreams.value.map((u) => u.id))
    selected.value = ids.filter((id) => alive.has(id))
  } catch {
    ElMessage.error(`批量${verb}失败`)
  }
}

/** 批量删除：逐条容错 + 与最新列表求交集，杜绝幽灵选中 */
async function batchDelete() {
  const ids = [...selected.value]
  if (!ids.length) return
  if (!await confirmDanger(`确定删除选中的 ${ids.length} 个上游源吗？`, '删除后引用它们的路由候选将失效。')) return

  const failed: string[] = []
  for (const id of ids) {
    try {
      await deleteUpstream(id)
    } catch {
      failed.push(id)
    }
  }

  const removed = ids.length - failed.length
  if (removed > 0) ElMessage.success(`已删除 ${removed} 个上游源`)
  if (failed.length) ElMessage.warning(`${failed.length} 个上游源删除失败，已保留选中`)

  await reloadConfig()
  await load()
  if ((page.value - 1) * pageSize.value >= filtered.value.length) page.value = 1
  const alive = new Set(upstreams.value.map((u) => u.id))
  selected.value = failed.filter((id) => alive.has(id))
}

const batchActions = computed(() => [
  { label: '批量启用', onClick: () => batchToggle(true) },
  { label: '批量禁用', onClick: () => batchToggle(false) },
  { label: '批量删除', variant: 'danger' as const, onClick: () => batchDelete() },
])

// ---------- 新增/修改表单 ----------
const formVisible = ref(false)
const formMode = ref<'add' | 'edit'>('add')
const formSaving = ref(false)
const form = reactive<UpstreamForm>(emptyForm())
const keyText = ref('')

// ---------- 手动添加模型 ----------
const manualModal = reactive({ visible: false, uid: '', input: '', saving: false })

const models = useUpstreamModels(() => load())
provide(UPSTREAM_MODELS_KEY, models)

async function load() {
  loading.value = true
  try {
    const [res, groups]: any = await Promise.all([listUpstreams(), listGroups()])
    upstreams.value = res.upstreams
    groupOptions.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
    for (const u of res.upstreams) {
      models.setModels(u.id, u.models || [])
      models.initUpstream(u.id)
    }
  } finally {
    loading.value = false
  }
  models.initAllSortables(upstreams.value.map((u: any) => u.id))
}

function openAdd() {
  formMode.value = 'add'
  Object.assign(form, emptyForm())
  keyText.value = ''
  formVisible.value = true
}

function openEdit(u: any) {
  formMode.value = 'edit'
  Object.assign(form, {
    id: u.id,
    name: u.name,
    base_url: u.base_url,
    format: u.format,
    groups: u.groups && u.groups.length ? [...u.groups] : [u.group || 'free'],
    probe_enabled: !!u.probe_enabled,
    smart_retry: !!u.smart_retry,
  })
  keyText.value = (u.keys || []).join('\n')
  formVisible.value = true
}

async function saveForm() {
  if (formMode.value === 'add') {
    const keys = parseKeys(keyText.value)
    if (!form.id || !form.name || !form.base_url || !keys.length) {
      ElMessage.warning('ID、名称、Base URL、API Key 均为必填')
      return
    }
    formSaving.value = true
    try {
      await addUpstream({
        id: form.id,
        name: form.name,
        base_url: form.base_url,
        api_keys: keys,
        format: form.format,
        groups: form.groups.length ? form.groups : ['free'],
        probe_enabled: form.probe_enabled,
        smart_retry: form.smart_retry,
      })
      ElMessage.success(`上游源 ${form.id} 添加成功`)
      formVisible.value = false
      await reloadConfig()
      load()
    } finally {
      formSaving.value = false
    }
    return
  }

  if (!form.name || !form.base_url) {
    ElMessage.warning('名称和 Base URL 为必填')
    return
  }
  formSaving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: form.name,
      base_url: form.base_url,
      format: form.format,
      groups: form.groups.length ? form.groups : ['free'],
      probe_enabled: form.probe_enabled,
      smart_retry: form.smart_retry,
    }
    const keys = parseKeys(keyText.value)
    if (keys.length) payload.api_keys = keys
    await updateUpstream(form.id, payload)
    ElMessage.success(`上游源「${form.name}」修改成功`)
    formVisible.value = false
    await reloadConfig()
    load()
  } finally {
    formSaving.value = false
  }
}

function openManualModal(u: any) {
  manualModal.uid = u.id
  manualModal.input = ''
  manualModal.saving = false
  manualModal.visible = true
}

async function confirmManualAdd() {
  const names = (manualModal.input || '')
    .split(/[,，\s]+/)
    .map((n: string) => n.trim())
    .filter((n: string) => n)
  if (!names.length) {
    ElMessage.warning('请输入模型名')
    return
  }
  manualModal.saving = true
  try {
    if (await models.addModels(manualModal.uid, names)) {
      ElMessage.success(`已添加 ${names.length} 个模型`)
      manualModal.visible = false
    }
  } finally {
    manualModal.saving = false
  }
}

async function handleToggle(u: any, val: boolean) {
  togglingIds.value.push(u.id)
  try {
    await updateUpstream(u.id, { enabled: val })
    u.enabled = val
    ElMessage.success(val ? `上游源「${u.name}」已启用` : `上游源「${u.name}」已禁用`)
    await reloadConfig()
  } catch {
    ElMessage.error('状态更新失败')
  } finally {
    togglingIds.value = togglingIds.value.filter((id) => id !== u.id)
  }
}

async function handleDelete(u: any) {
  if (!await confirmDanger(`确定删除上游源「${u.name}」吗？删除后引用它的路由候选将失效。`)) return
  await deleteUpstream(u.id)
  ElMessage.success('已删除')
  await reloadConfig()
  load()
}

onMounted(load)
</script>
