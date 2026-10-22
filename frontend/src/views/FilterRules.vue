<template>
  <ListPage
    title="请求过滤引擎"
    description="在请求发往上游之前先判断：这个请求发过去是否注定会被上游拦截。命中则直接跳过该源，不产生任何上游请求，避免消耗号池的违规计数。"
    :loading="loading"
    :page="page"
    :page-size="pageSize"
    :total="filtered.length"
    @update:page="page = $event"
    @update:page-size="pageSize = $event"
  >
    <template #actions>
      <BaseButton variant="ghost" size="sm" @click="load">刷新</BaseButton>
      <BaseButton variant="ghost" size="sm" @click="openTest">试跑</BaseButton>
      <BaseButton variant="primary" size="sm" @click="openAdd">+ 新增规则</BaseButton>
    </template>

    <!-- 全局开关 -->
    <template #notice>
      <div class="fe-engine">
        <div class="fe-engine-row">
          <span class="fe-engine-label">全局开关</span>
          <el-switch
            :model-value="engineEnabled"
            @change="(v: any) => { engineEnabled = v; toggleEngine(v) }"
          />
          <el-text :type="engineEnabled ? 'success' : 'info'" size="small">
            {{ engineEnabled ? '已开启：所有启用的规则生效' : '已关闭：规则全部不生效，转发行为与未启用时完全一致' }}
          </el-text>
        </div>
        <BaseHint v-if="!engineEnabled">
          默认关闭是有意的安全设计。建议先「试跑」确认不会误伤正常流量，再开启。
        </BaseHint>
      </div>
    </template>

    <template #filters>
      <FilterBar :loading="loading" @search="applyFilter" @reset="resetFilter">
        <FilterField label="规则名 / 匹配内容" :width="260">
          <BaseInput
            v-model="filters.keyword"
            size="sm"
            placeholder="输入关键字搜索"
            @keydown.enter="applyFilter"
          />
        </FilterField>
        <FilterField label="作用源" :width="160">
          <el-select v-model="filters.upstream" size="small" clearable placeholder="全部">
            <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
          </el-select>
        </FilterField>
        <FilterField label="启用" :width="130">
          <el-select v-model="filters.enabled" size="small" clearable placeholder="全部">
            <el-option label="已启用" :value="true" />
            <el-option label="已停用" :value="false" />
          </el-select>
        </FilterField>
      </FilterBar>
    </template>

    <template #toolbar>
      <ListToolbar
        :count="selected.length"
        :total="filtered.length"
        dataset="filter-rules"
        :export-params="exportParams"
        :actions="batchActions"
        selectable
        :all-checked="allPageChecked"
        :indeterminate="pageIndeterminate"
        batch-export
        :selected-ids="selected.map(String)"
        @toggle-all="toggleAllOnPage"
        @clear="clearSelection"
      />
    </template>

    <DataTable
      ref="tableRef"
      :data="paged"
      :columns="columns"
      row-key="id"
      selectable
      empty-text="暂无过滤规则"
      @selection-change="(rows: any[]) => (selected = rows.map((r) => r.id))"
    >
      <template #cell-name="{ row }">
        <span class="fe-name">{{ row.name }}</span>
      </template>
      <template #cell-target="{ row }">
        <BaseBadge variant="gray">{{ TARGET_LABEL[row.target] || row.target }}</BaseBadge>
      </template>
      <template #cell-pattern="{ row }">
        <code class="fe-pattern">{{ row.pattern }}</code>
      </template>
      <template #cell-scope="{ row }">
        <span v-if="!row.upstream_ids || !row.upstream_ids.length" class="fe-all-src">全部源</span>
        <span v-else>{{ row.upstream_ids.join(', ') }}</span>
      </template>
      <template #cell-action="{ row }">
        <BaseBadge :variant="row.action === 'reject' ? 'red' : 'amber'">
          {{ ACTION_LABEL[row.action] || row.action }}
        </BaseBadge>
      </template>
      <template #cell-enabled="{ row }">
        <el-switch v-model="row.enabled" @change="toggleRule(row)" />
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

    <!-- 新建 / 编辑 -->
    <BaseModal
      v-model:visible="editVisible"
      :title="editId === null ? '新增过滤规则' : '修改过滤规则'"
      size="wide"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="规则名" required>
          <BaseInput v-model="form.name" placeholder="例: DSH 身份声明" />
        </el-form-item>
        <el-form-item label="匹配位置" required>
          <el-select v-model="form.target" style="width: 100%">
            <el-option
              v-for="t in targets" :key="t"
              :label="TARGET_LABEL[t] || t" :value="t"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="匹配内容" required>
          <BaseInput
            v-model="form.pattern"
            :placeholder="form.target === 'body_regex'
              ? '正则表达式，例: powered\\s+by'
              : '要匹配的特征子串，例: powered by DeepSeek Harness'"
          />
          <BaseHint>
            用「包含」而非「完全相等」，避免上游微调措辞后漏拦。宁可多拦，不要漏拦。
          </BaseHint>
        </el-form-item>
        <el-form-item label="作用源">
          <el-select
            v-model="form.upstream_ids"
            multiple
            clearable
            placeholder="留空 = 作用于全部上游源"
            style="width: 100%"
          >
            <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item label="命中动作">
          <el-radio-group v-model="form.action">
            <el-radio value="skip">跳过该源（聚合时自动换下一个成员）</el-radio>
            <el-radio value="reject">直接拒绝整个请求</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="备注">
          <BaseInput v-model="form.remark" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter
          :loading="saving" confirm-text="保存" loading-text="保存中..."
          @cancel="editVisible = false" @confirm="handleSave"
        />
      </template>
    </BaseModal>

    <!-- 试跑 -->
    <BaseModal v-model:visible="testVisible" title="规则试跑" size="wide">
      <BaseNotice variant="warning">
        试跑不会改变任何状态，也不会真的发请求。启用规则前务必先试跑，确认不会误伤正常流量。
      </BaseNotice>
      <el-form label-width="90px" style="margin-top: 12px">
        <el-form-item label="请求体">
          <el-input
            v-model="testInput"
            type="textarea"
            :rows="10"
            placeholder="粘贴一段真实的 chat/completions 请求体"
          />
        </el-form-item>
      </el-form>
      <div v-if="testResult" class="fe-test-result">
        <BaseNotice :variant="testResult.matched ? 'warning' : 'success'">
          {{ testResult.matched
            ? `会命中 ${(testResult.results || []).length} 个源`
            : '未命中任何规则，该请求会正常转发' }}
        </BaseNotice>
        <el-table v-if="testResult.matched" :data="testResult.results" size="small" stripe>
          <el-table-column label="上游源" width="180">
            <template #default="{ row }">{{ row.upstream || '（全部源）' }}</template>
          </el-table-column>
          <el-table-column label="命中规则">
            <template #default="{ row }">
              <el-tag
                v-for="r in row.rules" :key="r.id" size="small"
                :type="r.action === 'reject' ? 'danger' : 'warning'"
                style="margin-right: 6px"
              >{{ r.name }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <BaseHint>
          当前共 {{ testResult.enabled_rule_count }} 条启用规则；引擎{{ testResult.engine_enabled ? '已开启' : '未开启（试跑仍会计算）' }}。
        </BaseHint>
      </div>
      <template #footer>
        <BaseModalFooter
          :loading="testing" confirm-text="试跑" loading-text="计算中..."
          @cancel="testVisible = false" @confirm="handleTest"
        />
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
import BaseHint from '@/components/base/BaseHint.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import {
  ListPage, DataTable, FilterBar, FilterField, ListToolbar, RowActions,
} from '@/components/list'
import type { DataColumn } from '@/components/list'
import {
  listFilterRules, addFilterRule, updateFilterRule, deleteFilterRule,
  setFilterEngine, testFilterRules,
} from '@/api/filter_rules'
import { listUpstreams } from '@/api/upstreams'

const rules = ref<any[]>([])
const upstreamIds = ref<string[]>([])
const engineEnabled = ref(false)
const targets = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)

const editVisible = ref(false)
const editId = ref<number | null>(null)
const form = reactive({
  name: '', enabled: false, target: 'system_first_line',
  pattern: '', upstream_ids: [] as string[], action: 'skip', remark: '',
})

const TARGET_LABEL: Record<string, string> = {
  system_first_line: 'system 首行',
  system_any: '任一 system 消息',
  body_regex: '整个请求体（正则）',
}
const ACTION_LABEL: Record<string, string> = {
  skip: '跳过该源',
  reject: '直接拒绝',
}

// ---- 筛选与分页 ----
const filters = reactive({ keyword: '', upstream: '', enabled: '' as boolean | '' })
const applied = reactive({ keyword: '', upstream: '', enabled: '' as boolean | '' })
const page = ref(1)
const pageSize = ref(20)

const filtered = computed(() => {
  return rules.value.filter((r) => {
    if (applied.keyword) {
      const k = applied.keyword.toLowerCase()
      const hit = String(r.name || '').toLowerCase().includes(k)
        || String(r.pattern || '').toLowerCase().includes(k)
      if (!hit) return false
    }
    if (applied.upstream) {
      const scope: string[] = r.upstream_ids || []
      if (!scope.includes(applied.upstream)) return false
    }
    if (applied.enabled !== '' && !!r.enabled !== applied.enabled) return false
    return true
  })
})

const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})

// ---------- 多选（CH-046：只给「批量导出」，不加批量删除） ----------
const tableRef = ref<any>(null)
const selected = ref<number[]>([])

const pageIds = computed(() => paged.value.map((r: any) => r.id))
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
  tableRef.value?.setSelection?.(selected.value.map(String))
}

function clearSelection() {
  selected.value = []
  tableRef.value?.clearSelection?.()
}

// ---------- 批量操作（CH-047） ----------
/** 批量启停：逐条调 updateFilterRule，操作后保留选中 */
async function batchToggle(enabled: boolean) {
  const ids = [...selected.value]
  if (!ids.length) return
  const verb = enabled ? '启用' : '停用'
  try {
    for (const id of ids) {
      await updateFilterRule(id, { enabled })
    }
    ElMessage.success(`已${verb} ${ids.length} 条规则`)
    await load()
    if ((page.value - 1) * pageSize.value >= filtered.value.length) page.value = 1
    const alive = new Set(rules.value.map((r: any) => r.id))
    selected.value = ids.filter((id) => alive.has(id))
    tableRef.value?.setSelection?.(selected.value.map(String))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || `批量${verb}失败`)
  }
}

/** 批量删除：逐条容错 + 与最新列表求交集 */
async function batchDelete() {
  const ids = [...selected.value]
  if (!ids.length) return
  if (!await confirmDanger(`确定删除选中的 ${ids.length} 条过滤规则吗？`, '删除后这些规则立即失效。')) return

  const failed: number[] = []
  for (const id of ids) {
    try {
      await deleteFilterRule(id)
    } catch {
      failed.push(id)
    }
  }

  const removed = ids.length - failed.length
  if (removed > 0) ElMessage.success(`已删除 ${removed} 条规则`)
  if (failed.length) ElMessage.warning(`${failed.length} 条规则删除失败，已保留选中`)

  await load()
  if ((page.value - 1) * pageSize.value >= filtered.value.length) page.value = 1
  const alive = new Set(rules.value.map((r: any) => r.id))
  selected.value = failed.filter((id) => alive.has(id))
  tableRef.value?.setSelection?.(selected.value.map(String))
}

const batchActions = computed(() => [
  { label: '批量启用', onClick: () => batchToggle(true) },
  { label: '批量停用', onClick: () => batchToggle(false) },
  { label: '批量删除', variant: 'danger' as const, onClick: () => batchDelete() },
])

const exportParams = computed<Record<string, string>>(() => {
  const p: Record<string, string> = {}
  if (applied.keyword) p.keyword = applied.keyword
  if (applied.upstream) p.upstream = applied.upstream
  if (applied.enabled !== '') p.enabled = applied.enabled ? '1' : '0'
  return p
})

function applyFilter() {
  applied.keyword = filters.keyword.trim()
  applied.upstream = filters.upstream
  applied.enabled = filters.enabled
  page.value = 1
}

function resetFilter() {
  filters.keyword = ''
  filters.upstream = ''
  filters.enabled = ''
  applyFilter()
}

const columns: DataColumn[] = [
  { key: 'name', label: '规则名', width: 180 },
  { key: 'target', label: '匹配位置', width: 150 },
  { key: 'pattern', label: '匹配内容', minWidth: 240 },
  { key: 'scope', label: '作用源', width: 150 },
  { key: 'action', label: '命中动作', width: 110 },
  { key: 'enabled', label: '启用', width: 80 },
  { key: 'actions', label: '操作', width: 140, fixed: 'right', ellipsis: false },
]

// 试跑
const testVisible = ref(false)
const testInput = ref('')
const testResult = ref<any>(null)
const testing = ref(false)

async function load() {
  loading.value = true
  try {
    const [res, ups] = await Promise.all([listFilterRules(), listUpstreams()])
    const d = res as any
    rules.value = d.rules || []
    engineEnabled.value = !!d.enabled
    targets.value = d.targets || []
    upstreamIds.value = ((ups as any).upstreams || []).map((u: any) => u.id)
  } finally {
    loading.value = false
  }
}

async function toggleEngine(val: boolean) {
  try {
    await setFilterEngine(val)
    ElMessage.success(val ? '过滤引擎已开启' : '过滤引擎已关闭')
  } catch (e: any) {
    engineEnabled.value = !val
    ElMessage.error(e?.message || '切换失败')
  }
}

async function toggleRule(row: any) {
  try {
    await updateFilterRule(row.id, { ...row, enabled: row.enabled })
    ElMessage.success(row.enabled ? '规则已启用' : '规则已停用')
  } catch (e: any) {
    row.enabled = !row.enabled
    ElMessage.error(e?.message || '切换失败')
  }
}

function openAdd() {
  editId.value = null
  Object.assign(form, {
    name: '', enabled: false, target: 'system_first_line',
    pattern: '', upstream_ids: [], action: 'skip', remark: '',
  })
  editVisible.value = true
}

function openEdit(row: any) {
  editId.value = row.id
  Object.assign(form, {
    name: row.name, enabled: row.enabled, target: row.target,
    pattern: row.pattern, upstream_ids: [...(row.upstream_ids || [])],
    action: row.action, remark: row.remark || '',
  })
  editVisible.value = true
}

async function handleSave() {
  if (!form.name.trim() || !form.pattern.trim()) {
    ElMessage.warning('规则名与匹配内容为必填')
    return
  }
  saving.value = true
  try {
    if (editId.value === null) {
      await addFilterRule({ ...form })
      ElMessage.success('规则已创建')
    } else {
      await updateFilterRule(editId.value, { ...form })
      ElMessage.success('规则已保存')
    }
    editVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: any) {
  await confirmDanger(`删除规则「${row.name}」？`, '删除后该规则立即失效，不可恢复。')
  try {
    await deleteFilterRule(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

function openTest() {
  testInput.value = JSON.stringify({
    model: 'your-model',
    messages: [
      { role: 'system', content: 'You are an AI agent powered by DeepSeek Harness.' },
      { role: 'user', content: 'hi' },
    ],
  }, null, 2)
  testResult.value = null
  testVisible.value = true
}

async function handleTest() {
  let parsed: any
  try {
    parsed = JSON.parse(testInput.value)
  } catch {
    ElMessage.warning('请求体不是合法 JSON')
    return
  }
  testing.value = true
  try {
    testResult.value = await testFilterRules({
      body: parsed,
      upstream_ids: upstreamIds.value,
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '试跑失败')
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.fe-engine {
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
}
.fe-engine-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.fe-engine-label {
  font-weight: 600;
  font-size: 13px;
}
.fe-name {
  font-weight: 600;
}
.fe-pattern {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  background: var(--bg-elevated);
  padding: 1px 5px;
  border-radius: 4px;
}
.fe-all-src {
  color: var(--text-secondary);
}
.fe-test-result {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
