<template>
  <ListPage
    title="模型别名管理"
    description="模型别名是指针：客户端请求别名时，直接转发到指定的真实模型，不走路由规则。可在后台随时切换指向。"
    :loading="loading"
    :page="page"
    :page-size="pageSize"
    :total="filtered.length"
    @update:page="page = $event"
    @update:page-size="pageSize = $event"
  >
    <template #actions>
      <BaseButton variant="ghost" size="sm" @click="load">刷新</BaseButton>
      <BaseButton variant="primary" size="sm" @click="openAdd">+ 新增别名</BaseButton>
    </template>

    <template #filters>
      <FilterBar :loading="loading" @search="applyFilter" @reset="resetFilter">
        <FilterField label="别名 / 目标模型" :width="240">
          <BaseInput
            v-model="filters.keyword"
            size="sm"
            placeholder="输入关键字搜索"
            @keydown.enter="applyFilter"
          />
        </FilterField>
        <FilterField label="上游源" :width="160">
          <el-select v-model="filters.upstream" size="small" clearable placeholder="全部">
            <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
          </el-select>
        </FilterField>
      </FilterBar>
    </template>

    <template #toolbar>
      <ListToolbar
        :count="selected.length"
        :total="filtered.length"
        dataset="pointers"
        :export-params="exportParams"
        :actions="batchActions"
        selectable
        :all-checked="allPageChecked"
        :indeterminate="pageIndeterminate"
        batch-export
        :selected-ids="selected"
        @toggle-all="toggleAllOnPage"
        @clear="clearSelection"
      />
    </template>

    <DataTable
      ref="tableRef"
      :data="paged"
      :columns="columns"
      row-key="name"
      selectable
      empty-text="暂无模型别名，请点击右上角「新增别名」"
      @selection-change="(rows: any[]) => (selected = rows.map((r) => r.name))"
    >
      <template #cell-name="{ row }">
        <span class="pl-name">{{ row.name }}</span>
      </template>
      <template #cell-target_model="{ row }">
        <code class="pl-code">{{ row.target_model }}</code>
      </template>
      <template #cell-upstream="{ row }">
        <BaseBadge variant="gray">{{ row.upstream || '—' }}</BaseBadge>
      </template>
      <template #cell-actions="{ row }">
        <RowActions
          :items="[
            { label: '修改', onClick: () => openEdit(row) },
            { label: '删除', variant: 'danger', onClick: () => handleDelete(row) },
          ]"
        />
      </template>
    </DataTable>

    <!-- 新增别名弹窗 -->
    <BaseModal v-model:visible="addVisible" title="新增别名" size="wide">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="别名名称" required>
          <BaseInput v-model="addForm.name" placeholder="例: my-model、gpt4" />
        </el-form-item>
        <el-form-item label="上游源" required>
          <el-select v-model="addForm.upstream" style="width: 100%" @change="onAddUpstreamChange">
            <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标模型" required>
          <el-select
            v-if="(modelsByUpstream[addForm.upstream] || []).length"
            v-model="addForm.target_model"
            filterable
            style="width: 100%"
          >
            <el-option v-for="m in modelsByUpstream[addForm.upstream]" :key="m" :label="m" :value="m" />
          </el-select>
          <BaseInput v-else v-model="addForm.target_model" placeholder="目标模型（手动输入）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter :loading="adding" confirm-text="确定添加" loading-text="添加中..."
          @cancel="addVisible = false" @confirm="handleAdd" />
      </template>
    </BaseModal>

    <!-- 修改别名弹窗 -->
    <BaseModal v-model:visible="editVisible" title="修改别名指向" size="wide">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="别名（不可改）">
          <el-input :model-value="editForm.name" disabled />
        </el-form-item>
        <el-form-item label="上游源" required>
          <el-select v-model="editForm.upstream" style="width: 100%" @change="onEditUpstreamChange">
            <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标模型" required>
          <el-select
            v-if="(modelsByUpstream[editForm.upstream] || []).length"
            v-model="editForm.target_model"
            filterable
            style="width: 100%"
          >
            <el-option v-for="m in modelsByUpstream[editForm.upstream]" :key="m" :label="m" :value="m" />
          </el-select>
          <BaseInput v-else v-model="editForm.target_model" placeholder="目标模型（手动输入）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter :loading="editing" confirm-text="保存修改"
          @cancel="editVisible = false" @confirm="handleEditSave" />
      </template>
    </BaseModal>
  </ListPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import {
  ListPage, DataTable, FilterBar, FilterField, ListToolbar, RowActions,
} from '@/components/list'
import type { DataColumn } from '@/components/list'
import { addPointer, deletePointer, listPointers, updatePointer } from '@/api/pointers'
import { listUpstreams } from '@/api/upstreams'
import { listSourceModels } from '@/api/model_groups'
import { reloadConfig } from '@/api/common'

const pointers = ref<any[]>([])
const upstreamIds = ref<string[]>([])
const modelsByUpstream = reactive<Record<string, string[]>>({})
const loading = ref(false)
const adding = ref(false)
const editing = ref(false)

const addVisible = ref(false)
const editVisible = ref(false)

const editForm = reactive({ name: '', target_model: '', upstream: '' })
const addForm = reactive({ name: '', target_model: '', upstream: '' })

// ---- 筛选与分页（前端过滤，别名数量级很小） ----
const filters = reactive({ keyword: '', upstream: '' })
const applied = reactive({ keyword: '', upstream: '' })
const page = ref(1)
const pageSize = ref(20)

const filtered = computed(() => {
  return pointers.value.filter((r) => {
    if (applied.keyword) {
      const k = applied.keyword.toLowerCase()
      const hit = String(r.name || '').toLowerCase().includes(k)
        || String(r.target_model || '').toLowerCase().includes(k)
      if (!hit) return false
    }
    if (applied.upstream && r.upstream !== applied.upstream) return false
    return true
  })
})

const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})

// ---------- 多选（CH-046：只给「批量导出」，不加批量删除） ----------
const tableRef = ref<any>(null)
const selected = ref<string[]>([])

const pageNames = computed(() => paged.value.map((r: any) => r.name))
const allPageChecked = computed(() =>
  pageNames.value.length > 0 && pageNames.value.every((n) => selected.value.includes(n)),
)
const pageIndeterminate = computed(() => {
  const hit = pageNames.value.filter((n) => selected.value.includes(n)).length
  return hit > 0 && hit < pageNames.value.length
})

function toggleAllOnPage(checked: boolean) {
  if (checked) {
    selected.value = [...new Set([...selected.value, ...pageNames.value])]
  } else {
    const drop = new Set(pageNames.value)
    selected.value = selected.value.filter((n) => !drop.has(n))
  }
  tableRef.value?.setSelection?.(selected.value)
}

function clearSelection() {
  selected.value = []
  tableRef.value?.clearSelection?.()
}

/** 批量删除（CH-047）：逐条容错 + 与最新列表求交集，杜绝幽灵选中 */
async function batchDelete() {
  const names = [...selected.value]
  if (!names.length) return
  if (!await confirmDanger(`确定删除选中的 ${names.length} 个模型别名吗？`, '删除后客户端请求这些别名将不再被转发。')) return

  const failed: string[] = []
  for (const name of names) {
    try {
      await deletePointer(name)
    } catch {
      failed.push(name)
    }
  }

  const removed = names.length - failed.length
  if (removed > 0) ElMessage.success(`已删除 ${removed} 个别名`)
  if (failed.length) ElMessage.warning(`${failed.length} 个别名删除失败，已保留选中`)

  await reloadConfig()
  await load()
  if ((page.value - 1) * pageSize.value >= filtered.value.length) page.value = 1

  const alive = new Set(pointers.value.map((r: any) => r.name))
  selected.value = failed.filter((n) => alive.has(n))
  tableRef.value?.setSelection?.(selected.value)
}

const batchActions = computed(() => [
  { label: '批量删除', variant: 'danger' as const, onClick: () => batchDelete() },
])

/** 导出参数：把当前生效的筛选条件带给后端，导出的就是「你看到的这批」 */
const exportParams = computed<Record<string, string>>(() => {
  const p: Record<string, string> = {}
  if (applied.keyword) p.keyword = applied.keyword
  if (applied.upstream) p.upstream = applied.upstream
  return p
})

function applyFilter() {
  applied.keyword = filters.keyword.trim()
  applied.upstream = filters.upstream
  page.value = 1
}

function resetFilter() {
  filters.keyword = ''
  filters.upstream = ''
  applyFilter()
}

const columns: DataColumn[] = [
  { key: 'name', label: '别名', width: 200 },
  { key: 'target_model', label: '目标模型', minWidth: 240 },
  { key: 'upstream', label: '上游源', width: 140 },
  { key: 'actions', label: '操作', width: 140, fixed: 'right', ellipsis: false },
]

async function load() {
  loading.value = true
  try {
    const [ptRes, upsRes] = await Promise.all([listPointers(), listUpstreams()])
    pointers.value = (ptRes as any).pointers
    upstreamIds.value = (upsRes as any).upstreams.map((u: any) => u.id)
    if (upstreamIds.value.length && !addForm.upstream) addForm.upstream = upstreamIds.value[0]
    upstreamIds.value.forEach((id) => {
      // 读该源「已配置模型」，不依赖上游是否可达（CH-028）
      listSourceModels(id)
        .then((r: any) => (modelsByUpstream[id] = ((r.models || []) as any[]).map((m) => m.name)))
        .catch(() => {})
    })
  } finally {
    loading.value = false
  }
}

function openAdd() {
  addForm.name = ''
  addForm.target_model = ''
  addForm.upstream = upstreamIds.value[0] || ''
  addVisible.value = true
}

function openEdit(row: any) {
  editForm.name = row.name
  editForm.target_model = row.target_model
  editForm.upstream = row.upstream
  editVisible.value = true
}

function onAddUpstreamChange() {
  addForm.target_model = ''
}

function onEditUpstreamChange() {
  editForm.target_model = ''
}

async function handleAdd() {
  if (!addForm.name || !addForm.target_model) {
    ElMessage.warning('别名名称和目标模型为必填')
    return
  }
  adding.value = true
  try {
    await addPointer({ ...addForm })
    ElMessage.success(`别名 ${addForm.name} 添加成功`)
    addVisible.value = false
    await reloadConfig()
    load()
  } finally {
    adding.value = false
  }
}

async function handleEditSave() {
  if (!editForm.target_model) {
    ElMessage.warning('请选择目标模型')
    return
  }
  editing.value = true
  try {
    await updatePointer(editForm.name, { target_model: editForm.target_model, upstream: editForm.upstream })
    ElMessage.success(`别名 ${editForm.name} 已指向 ${editForm.target_model}`)
    editVisible.value = false
    await reloadConfig()
    load()
  } finally {
    editing.value = false
  }
}

async function handleDelete(row: any) {
  if (!await confirmDanger(`确定删除别名「${row.name}」吗？`)) return
  await deletePointer(row.name)
  ElMessage.success('已删除')
  await reloadConfig()
  load()
}

onMounted(load)
</script>

<style scoped>
.pl-name {
  font-weight: 600;
}

.pl-code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  background: var(--bg-elevated);
  padding: 1px 6px;
  border-radius: 4px;
}
</style>
