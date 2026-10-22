<template>
  <ListPage
    title="路由层 API Key 管理"
    description="这些 Key 是客户端访问 Smart Router 的入场券。校验通过后，路由器会用各 upstream 自己的 Key 去访问模型提供商。"
    :loading="loading"
    :page="page"
    :page-size="pageSize"
    :total="filtered.length"
    @update:page="page = $event"
    @update:page-size="pageSize = $event"
  >
    <template #actions>
      <BaseButton variant="ghost" size="sm" @click="load">刷新</BaseButton>
      <BaseButton variant="primary" size="sm" @click="openAdd">+ 新增 Key</BaseButton>
    </template>

    <template #filters>
      <FilterBar :loading="loading" @search="applyFilter" @reset="resetFilter">
        <FilterField label="名称 / Key" :width="260">
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
        dataset="api-keys"
        batch-export
        :export-params="exportParams"
        :selected-ids="selected.map((r: any) => r.key)"
        @clear="clearSelection"
      />
    </template>

    <DataTable
      ref="tableRef"
      :data="paged"
      :columns="columns"
      row-key="key"
      selectable
      empty-text="暂无 API Key，请点击右上角「新增 Key」"
      @selection-change="(rows: any[]) => (selected = rows)"
    >
      <template #cell-name="{ row }">
        <span class="ak-name">{{ row.name }}</span>
      </template>
      <template #cell-key="{ row }">
        <code class="ak-code">{{ row.key_masked }}</code>
      </template>
      <template #cell-groups="{ row }">
        <BaseBadge v-for="g in row.groups" :key="g" variant="default" style="margin-right: 4px">
          {{ g }}
        </BaseBadge>
      </template>
      <template #cell-enabled="{ row }">
        <BaseBadge :variant="row.enabled ? 'green' : 'red'">
          {{ row.enabled ? '启用' : '禁用' }}
        </BaseBadge>
      </template>
      <template #cell-actions="{ row }">
        <RowActions
          :items="[
            { label: '修改', onClick: () => openEdit(row) },
            { label: '复制', onClick: () => showCopy(row) },
            { label: '说明', onClick: () => openUsage(row) },
            { label: '删除', variant: 'danger', divider: true, onClick: () => handleDelete(row) },
          ]"
        />
      </template>
    </DataTable>

    <!-- 新增 Key 弹窗 -->
    <BaseModal v-model:visible="addVisible" title="新增 API Key" size="wide">
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="名称">
          <BaseInput v-model="addForm.name" placeholder="例: 扣子平台、开发测试" />
        </el-form-item>
        <el-form-item label="Key 值" required>
          <div class="key-input-row">
            <BaseInput v-model="addForm.key" type="password" placeholder="sk-my-key-123" show-password />
            <BaseButton variant="ghost" size="sm" @click="regenerate">重新生成</BaseButton>
          </div>
          <BaseHint text="已自动生成随机 Key，也可手动修改或点击「重新生成」换一个" />
        </el-form-item>
        <el-form-item label="分组">
          <el-select v-model="addForm.groups" multiple placeholder="选择分组" style="width: 100%">
            <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
          <BaseHint text="该 Key 只能访问所选分组的上游源" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter :loading="adding" confirm-text="确定添加" loading-text="添加中..."
          @cancel="addVisible = false" @confirm="handleAdd" />
      </template>
    </BaseModal>

    <!-- 修改 Key 弹窗 -->
    <BaseModal v-model:visible="editVisible" title="修改 API Key" size="wide">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="Key（不可改）">
          <el-input :model-value="editForm.key" disabled />
        </el-form-item>
        <el-form-item label="名称">
          <BaseInput v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="分组">
          <el-select v-model="editForm.groups" multiple placeholder="选择分组" style="width: 100%">
            <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="editForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter :loading="editing" confirm-text="保存修改"
          @cancel="editVisible = false" @confirm="handleEditSave" />
      </template>
    </BaseModal>

    <!-- 接入说明弹窗 -->
    <BaseModal v-model:visible="usageVisible" :title="`接入说明：${usageKey?.name || ''}`" size="wide">
      <div v-if="usageKey" class="usage-body">
        <div class="usage-block">
          <div class="usage-label">请求地址（OpenAI 兼容）</div>
          <div class="usage-code-row">
            <code>{{ apiBase }}/v1/chat/completions</code>
            <BaseButton variant="ghost" size="sm" @click="copyText(`${apiBase}/v1/chat/completions`)">复制</BaseButton>
          </div>
          <BaseHint>流式：请求体加 "stream": true；模型列表：GET {{ apiBase }}/v1/models</BaseHint>
        </div>

        <div class="usage-block">
          <div class="usage-label">鉴权（API Key）</div>
          <div class="usage-code-row">
            <code>Authorization: Bearer {{ usageKey.key }}</code>
            <BaseButton variant="ghost" size="sm" @click="copyText(usageKey.key)">复制 Key</BaseButton>
          </div>
        </div>

        <div class="usage-block">
          <div class="usage-label">该 Key 可用模型（分组：{{ (usageKey.groups || []).join('、') || 'free' }}）</div>
          <div v-if="usageModels.length" class="usage-models">
            <BaseBadge v-for="m in usageModels.slice(0, 30)" :key="m" variant="default" style="margin: 0 4px 4px 0">{{ m }}</BaseBadge>
            <el-text v-if="usageModels.length > 30" type="info" size="small">等共 {{ usageModels.length }} 个</el-text>
          </div>
          <el-text v-else type="info" size="small">该分组下暂无已配置模型的上游源；别名与聚合模型名也可作为 model 使用</el-text>
        </div>

        <div class="usage-block">
          <div class="usage-label-row">
            <span class="usage-label">curl 示例</span>
            <BaseButton variant="ghost" size="sm" @click="copyText(curlExample)">复制示例</BaseButton>
          </div>
          <pre class="usage-pre">{{ curlExample }}</pre>
        </div>

        <div class="usage-block">
          <div class="usage-label-row">
            <span class="usage-label">Python（OpenAI SDK）示例</span>
            <BaseButton variant="ghost" size="sm" @click="copyText(pythonExample)">复制示例</BaseButton>
          </div>
          <pre class="usage-pre">{{ pythonExample }}</pre>
        </div>
      </div>
    </BaseModal>
  </ListPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import {
  ListPage, DataTable, FilterBar, FilterField, ListToolbar, RowActions,
} from '@/components/list'
import type { DataColumn, RowActionItem } from '@/components/list'
import { addApiKey, deleteApiKey, listApiKeys, updateApiKey } from '@/api/apiKeys'
import { listUpstreams } from '@/api/upstreams'
import { reloadConfig } from '@/api/common'
import { listGroups } from '@/api/groups'
import { copyToClipboard } from '@/utils/clipboard'

const keys = ref<any[]>([])
const loading = ref(false)
const adding = ref(false)
const editing = ref(false)
const groupOptions = ref<{ name: string; description: string }[]>([])

const addVisible = ref(false)
const editVisible = ref(false)

// 接入说明弹窗
const usageVisible = ref(false)
const usageKey = ref<any>(null)
const upstreamList = ref<any[]>([])
const apiBase = location.origin

function openUsage(row: any) {
  usageKey.value = row
  usageVisible.value = true
}

const usageModels = computed<string[]>(() => {
  if (!usageKey.value) return []
  const groups = new Set(usageKey.value.groups || ['free'])
  const all = groups.has('*')
  const set = new Set<string>()
  for (const u of upstreamList.value) {
    if (!u.enabled) continue
    if (!all && !groups.has(u.group)) continue
    for (const m of u.models || []) {
      if (m?.name) set.add(m.name)
    }
  }
  return [...set].sort()
})

const demoModel = computed(() => usageModels.value[0] || 'deepseek-v4-flash')

const curlExample = computed(() => {
  if (!usageKey.value) return ''
  return `curl ${apiBase}/v1/chat/completions \\
  -H "Authorization: Bearer ${usageKey.value.key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"${demoModel.value}","messages":[{"role":"user","content":"你好"}]}'`
})

const pythonExample = computed(() => {
  if (!usageKey.value) return ''
  return `from openai import OpenAI

client = OpenAI(
    base_url="${apiBase}/v1",
    api_key="${usageKey.value.key}",
)

resp = client.chat.completions.create(
    model="${demoModel.value}",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)`
})

async function copyText(text: string) {
  const ok = await copyToClipboard(text)
  if (ok) ElMessage.success('已复制到剪贴板')
  else ElMessage.error('复制失败，请手动选择复制')
}

const addForm = reactive({ name: '', key: '', groups: ['free'] as string[] })
const editForm = reactive({ key: '', name: '', groups: [] as string[], enabled: true })

// ---- 筛选 / 分页 / 多选 ----
const filters = reactive({ keyword: '', group: '', enabled: '' as boolean | '' })
const applied = reactive({ keyword: '', group: '', enabled: '' as boolean | '' })
const page = ref(1)
const pageSize = ref(20)
const selected = ref<any[]>([])
const tableRef = ref<any>(null)

const filtered = computed(() => {
  return keys.value.filter((k) => {
    if (applied.keyword) {
      const kw = applied.keyword.toLowerCase()
      const hit = String(k.name || '').toLowerCase().includes(kw)
        || String(k.key || '').toLowerCase().includes(kw)
      if (!hit) return false
    }
    if (applied.group && !(k.groups || []).includes(applied.group)) return false
    if (applied.enabled !== '' && !!k.enabled !== applied.enabled) return false
    return true
  })
})

const enabledCount = computed(() => filtered.value.filter((k) => k.enabled).length)

const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})

const exportParams = computed<Record<string, string>>(() => {
  const p: Record<string, string> = {}
  if (applied.keyword) p.keyword = applied.keyword
  if (applied.group) p.group = applied.group
  if (applied.enabled !== '') p.enabled = applied.enabled ? '1' : '0'
  return p
})

const columns: DataColumn[] = [
  { key: 'name', label: '名称', width: 170 },
  { key: 'key', label: 'Key', minWidth: 200 },
  { key: 'groups', label: '分组', width: 180 },
  { key: 'enabled', label: '状态', width: 100 },
  { key: 'actions', label: '操作', width: 230, fixed: 'right', ellipsis: false },
]

/** 批量操作：未选中时由 ListToolbar 自动置灰 */
const batchActions = computed<RowActionItem[]>(() => [
  {
    label: '批量启用',
    onClick: () => batchToggle(true),
  },
  {
    label: '批量禁用',
    onClick: () => batchToggle(false),
  },
  {
    label: '批量删除',
    variant: 'danger',
    onClick: batchDelete,
  },
])

function clearSelection() {
  tableRef.value?.clearSelection?.()
  selected.value = []
}

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

function genKey(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  let s = ''
  for (let i = 0; i < 28; i++) s += chars[Math.floor(Math.random() * chars.length)]
  return 'sk-sr-' + s
}

function regenerate() {
  addForm.key = genKey()
}

async function load() {
  loading.value = true
  try {
    const [res, groups, ups]: any = await Promise.all([listApiKeys(), listGroups(), listUpstreams()])
    keys.value = res.api_keys
    groupOptions.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
    upstreamList.value = ups.upstreams || []
  } finally {
    loading.value = false
  }
}

function openAdd() {
  addForm.name = ''
  addForm.key = genKey()
  addForm.groups = ['free']
  addVisible.value = true
}

function openEdit(row: any) {
  editForm.key = row.key
  editForm.name = row.name
  editForm.groups = [...(row.groups || [])]
  editForm.enabled = !!row.enabled
  editVisible.value = true
}

async function showCopy(row: any) {
  const ok = await copyToClipboard(row.key)
  if (ok) ElMessage.success('已复制到剪贴板')
  else ElMessage.error('复制失败，请手动选择复制')
}

/**
 * 批量启停：逐条调用现有 update 接口（后端没有批量端点，保持行为一致最重要）
 *
 * CH-043：操作完**保留选中**——用户常要连续点「禁用 → 再启用」，
 * 每次都重新勾选很烦。reload 后按 key 回填勾选。
 */
async function batchToggle(enabled: boolean) {
  const rows = selected.value
  if (!rows.length) return
  const verb = enabled ? '启用' : '禁用'
  const keepKeys = rows.map((r: any) => r.key)
  try {
    for (const row of rows) {
      await updateApiKey(row.key, { enabled })
    }
    ElMessage.success(`已${verb} ${keepKeys.length} 个 Key`)
    await reloadConfig()
    await load()
    // 数据换了新对象，按 key 把勾选补回去
    tableRef.value?.setSelection?.(keepKeys)
  } catch {
    ElMessage.error(`批量${verb}失败`)
  }
}

/**
 * 批量删除
 *
 * CH-043：删完必须重新核对选中 —— 已删除的行不能继续留在 selected 里，
 * 否则工具条会显示「已选 N 项」但表格里一条都没有，再点批量删除会去删不存在的记录。
 * 做法：删除后与最新列表求交集，只保留仍然存在的行。
 */
async function batchDelete() {
  const rows = selected.value
  if (!rows.length) return
  const ok = await confirmDanger(`确定删除选中的 ${rows.length} 个 Key 吗？`, '删除后使用这些 Key 的客户端将立即无法访问。')
  if (!ok) return

  const tryKeys = rows.map((r: any) => r.key)
  const failed: string[] = []
  for (const key of tryKeys) {
    try {
      await deleteApiKey(key)
    } catch {
      failed.push(key)
    }
  }

  const deleted = tryKeys.length - failed.length
  if (deleted > 0) ElMessage.success(`已删除 ${deleted} 个 Key`)
  if (failed.length) ElMessage.warning(`${failed.length} 个 Key 删除失败，已保留选中`)

  await reloadConfig()
  await load()

  if (!failed.length) {
    // 全部删成功：选中彻底清空
    clearSelection()
  } else {
    // 部分失败：只保留仍在最新列表里的（避免幽灵选中）
    const aliveKeys = new Set(keys.value.map((k: any) => String(k.key)))
    const keep = failed.filter((k) => aliveKeys.has(String(k)))
    tableRef.value?.setSelection?.(keep)
  }
}

async function handleDelete(row: any) {
  if (!await confirmDanger(`确定删除 Key「${row.name}」吗？删除后客户端将无法使用此 Key 访问。`)) return
  await deleteApiKey(row.key)
  ElMessage.success('已删除')
  await reloadConfig()
  load()
}

async function handleAdd() {
  if (!addForm.key) {
    ElMessage.warning('Key 值为必填')
    return
  }
  adding.value = true
  try {
    await addApiKey({
      name: addForm.name || '未命名',
      key: addForm.key,
      groups: addForm.groups.length ? addForm.groups : ['free'],
    })
    ElMessage.success('API Key 添加成功')
    addVisible.value = false
    await reloadConfig()
    load()
  } finally {
    adding.value = false
  }
}

async function handleEditSave() {
  editing.value = true
  try {
    await updateApiKey(editForm.key, {
      name: editForm.name,
      groups: editForm.groups.length ? editForm.groups : ['free'],
      enabled: editForm.enabled,
    })
    ElMessage.success('API Key 修改成功')
    editVisible.value = false
    await reloadConfig()
    load()
  } finally {
    editing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.ak-name {
  font-weight: 600;
}
.ak-code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  color: var(--text-secondary);
}
.key-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.key-input-row .base-input {
  flex: 1;
}
.usage-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.usage-label {
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 6px;
}
.usage-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.usage-label-row .usage-label {
  margin-bottom: 0;
}
.usage-code-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.usage-code-row code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.82rem;
  background: var(--bg-elevated);
  padding: 6px 10px;
  border-radius: 6px;
  word-break: break-all;
  flex: 1;
}
.usage-models {
  display: flex;
  flex-wrap: wrap;
}
.usage-pre {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
  background: var(--bg-elevated);
  padding: 10px 12px;
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre;
  margin: 0 0 6px;
  line-height: 1.6;
}
</style>
