<template>
  <div>
    <ListPage
      title="用量统计"
      description="全局汇总、按模型 / 按单元（号池核算）/ 按 Key 三层统计，以及最近请求明细。"
      :loading="loading"
      :pagination="false"
    >
      <template #actions>
        <el-radio-group v-model="range" size="small" @change="load">
          <el-radio-button value="today">今日</el-radio-button>
          <el-radio-button value="7d">近 7 天</el-radio-button>
          <el-radio-button value="30d">近 30 天</el-radio-button>
        </el-radio-group>
        <BaseButton variant="ghost" size="sm" @click="load">刷新</BaseButton>
      </template>

      <!-- 汇总指标卡 -->
      <div class="usage-stat-grid">
        <StatCard label="请求总数" :value="summary.total" hint="所选时间范围内的全部请求" />
        <StatCard label="总 Tokens" :value="formatTokens(summary.total_tokens)" hint="输入 + 输出" />
        <StatCard
          label="成功率"
          :value="summary.success_rate === null ? '—' : (summary.success_rate * 100).toFixed(1) + '%'"
          :tone="rateTone"
          hint="成功请求 / 总请求"
        />
        <StatCard label="活跃 Key" :value="summary.active_keys" hint="该时段内有请求的客户端 Key 数" />
        <StatCard
          label="已过滤"
          :value="summary.filtered_count || 0"
          tone="warning"
          hint="命中过滤规则、未发往上游的请求。这些请求不消耗号池额度，也不会计入上游违规。"
        />
      </div>

      <!-- 高频错误 -->
      <div v-if="summary.top_errors?.length" class="usage-error-top">
        <span class="usage-error-label">高频错误：</span>
        <el-tag
          v-for="e in summary.top_errors" :key="e.target"
          type="danger" size="small" style="margin-right: 8px"
        >
          {{ e.target }} × {{ e.count }}
        </el-tag>
      </div>

      <!--
        CH-046：三张汇总表各自拆成独立 ListPage（不再共用一个外层）。
        每张表有自己的标题、右上操作、常驻工具条、全选与底部分页，
        与 API Key 页形态一致。
      -->
      <ListPage
        title="按模型"
        style="margin-top: 16px"
        :page="modelPage"
        :page-size="modelSize"
        :total="filteredModel.length"
        @update:page="modelPage = $event"
        @update:page-size="modelSize = $event"
      >
        <template #filters>
          <FilterBar @search="modelPage = 1" @reset="resetModelFilter">
            <FilterField label="模型名" :width="280">
              <BaseInput
                v-model="modelKeyword"
                size="sm"
                placeholder="输入模型名过滤"
                @keydown.enter="modelPage = 1"
              />
            </FilterField>
          </FilterBar>
        </template>

        <template #toolbar>
          <ListToolbar
            :count="selectedModels.length"
            :total="filteredModel.length"
            dataset="usage-by-model"
            :export-params="{ range }"
            selectable
            :all-checked="allModelChecked"
            :indeterminate="modelIndeterminate"
            batch-export
            :selected-ids="selectedModels"
            @toggle-all="toggleAllModels"
            @clear="selectedModels = []"
          />
        </template>

        <DataTable
          :data="pagedByModel"
          :columns="modelColumns"
          row-key="model"
          selectable
          empty-text="暂无数据"
          @selection-change="(rows: any[]) => (selectedModels = rows.map((r) => r.model))"
        >
          <template #cell-model="{ row }">
            <code class="usage-code">{{ row.model }}</code>
          </template>
          <template #cell-error_count="{ row }">
            <span :class="{ 'usage-error': row.error_count > 0 }">{{ row.error_count }}</span>
          </template>
          <template #cell-avg_duration_ms="{ row }">
            {{ row.avg_duration_ms ? row.avg_duration_ms + 'ms' : '—' }}
          </template>
        </DataTable>
      </ListPage>

      <ListPage
        title="按单元（上游源 × 真实模型）"
        description="号池积分消耗核算，聚合请求会落到真实模型名"
        style="margin-top: 16px"
        :page="unitPage"
        :page-size="unitSize"
        :total="filteredUnit.length"
        @update:page="unitPage = $event"
        @update:page-size="unitSize = $event"
      >
        <template #filters>
          <FilterBar @search="unitPage = 1" @reset="resetUnitFilter">
            <FilterField label="上游源 / 模型名" :width="320">
              <BaseInput
                v-model="unitKeyword"
                size="sm"
                placeholder="输入上游源或真实模型名过滤"
                @keydown.enter="unitPage = 1"
              />
            </FilterField>
          </FilterBar>
        </template>

        <template #toolbar>
          <ListToolbar
            :count="selectedUnits.length"
            :total="filteredUnit.length"
            dataset="usage-by-unit"
            :export-params="{ range }"
            selectable
            :all-checked="allUnitChecked"
            :indeterminate="unitIndeterminate"
            batch-export
            :selected-ids="selectedUnits"
            @toggle-all="toggleAllUnits"
            @clear="selectedUnits = []"
          />
        </template>

        <DataTable
          :data="pagedByUnit"
          :columns="unitColumns"
          row-key="__k"
          selectable
          empty-text="暂无数据"
          @selection-change="(rows: any[]) => (selectedUnits = rows.map((r) => r.__k))"
        >
          <template #cell-upstream="{ row }">
            {{ row.upstream_name || row.upstream_id }}
          </template>
          <template #cell-upstream_model="{ row }">
            <code class="usage-code">{{ row.upstream_model }}</code>
          </template>
          <template #cell-error_count="{ row }">
            <span :class="{ 'usage-error': row.error_count > 0 }">{{ row.error_count }}</span>
          </template>
          <template #cell-total_tokens="{ row }">{{ formatTokens(row.total_tokens) }}</template>
          <template #cell-avg_duration_ms="{ row }">
            {{ row.avg_duration_ms ? row.avg_duration_ms + 'ms' : '—' }}
          </template>
        </DataTable>
      </ListPage>

      <ListPage
        title="按 API Key"
        style="margin-top: 16px"
        :page="keyPage"
        :page-size="keySize"
        :total="filteredKey.length"
        @update:page="keyPage = $event"
        @update:page-size="keySize = $event"
      >
        <template #filters>
          <FilterBar @search="keyPage = 1" @reset="resetKeyFilter">
            <FilterField label="Key 名称" :width="280">
              <BaseInput
                v-model="keyKeyword"
                size="sm"
                placeholder="输入 Key 名称过滤"
                @keydown.enter="keyPage = 1"
              />
            </FilterField>
          </FilterBar>
        </template>

        <template #toolbar>
          <ListToolbar
            :count="selectedKeys.length"
            :total="filteredKey.length"
            dataset="usage-by-key"
            :export-params="{ range }"
            selectable
            :all-checked="allKeyChecked"
            :indeterminate="keyIndeterminate"
            batch-export
            :selected-ids="selectedKeys"
            @toggle-all="toggleAllKeys"
            @clear="selectedKeys = []"
          />
        </template>

        <DataTable
          :data="pagedByKey"
          :columns="keyColumns"
          row-key="__k"
          selectable
          empty-text="暂无数据"
          @selection-change="(rows: any[]) => (selectedKeys = rows.map((r) => r.__k))"
        >
          <template #cell-api_key_name="{ row }">
            {{ row.api_key_name || `#${row.api_key_id}` }}
          </template>
          <template #cell-error_count="{ row }">
            <span :class="{ 'usage-error': row.error_count > 0 }">{{ row.error_count }}</span>
          </template>
          <template #cell-avg_duration_ms="{ row }">
            {{ row.avg_duration_ms ? row.avg_duration_ms + 'ms' : '—' }}
          </template>
        </DataTable>
      </ListPage>

      <!-- 最近请求明细 -->
      <ListPage
        title="最近请求明细"
        description="点击任意一行查看原始请求 / 实际转发 / 上游响应 三栏对比"
        style="margin-top: 16px"
        :loading="logsLoading"
        :page="logPage"
        :page-size="logSize"
        :total="logTotal"
        @update:page="logPage = $event"
        @update:page-size="logSize = $event"
        @change="loadLogs"
      >
        <template #filters>
          <FilterBar :loading="logsLoading" @search="loadLogs" @reset="resetLogFilters">
            <FilterField label="状态" :width="140">
              <el-select v-model="logStatus" size="small" clearable placeholder="全部状态">
                <el-option label="成功" value="success" />
                <el-option label="失败" value="error" />
                <el-option label="已过滤" value="filtered" />
              </el-select>
            </FilterField>
            <FilterField label="模型名" :width="240">
              <BaseInput
                v-model="logModel"
                size="sm"
                placeholder="按模型名过滤"
                @keydown.enter="loadLogs"
              />
            </FilterField>
          </FilterBar>
        </template>

        <template #toolbar>
          <ListToolbar
            :count="selectedLogs.length"
            :total="logTotal"
            dataset="usage-logs"
            :export-params="logExportParams"
            selectable
            :all-checked="allLogChecked"
            :indeterminate="logIndeterminate"
            batch-export
            :selected-ids="selectedLogs.map(String)"
            @toggle-all="toggleAllLogs"
            @clear="clearLogSelection"
          />
        </template>

        <DataTable
          ref="logTableRef"
          :data="logs"
          :columns="logColumns"
          row-key="id"
          selectable
          clickable-row
          empty-text="暂无请求记录"
          @row-click="openDetail"
          @selection-change="(rows: any[]) => (selectedLogs = rows.map((r) => r.id))"
        >
          <template #cell-created_at="{ row }">{{ formatTime(row.created_at) }}</template>
          <template #cell-api_key_name="{ row }">{{ row.api_key_name || '—' }}</template>
          <template #cell-model="{ row }">
            <code class="usage-code">{{ row.model }}</code>
          </template>
          <template #cell-upstream="{ row }">{{ row.upstream_name || row.upstream_id || '—' }}</template>
          <template #cell-protocol="{ row }">
            <BaseBadge variant="gray">{{ row.protocol }}{{ row.stream ? ' ·流式' : '' }}</BaseBadge>
          </template>
          <template #cell-status="{ row }">
            <!-- CH-041：被过滤引擎拦截（未发往上游），与普通失败区分开 -->
            <BaseBadge
              v-if="(row.error_msg || '').startsWith('【已过滤】')"
              variant="amber"
            >已过滤</BaseBadge>
            <BaseBadge v-else :variant="row.status === 'success' ? 'green' : (row.http_status === 499 ? 'amber' : 'red')">
              {{ row.status === 'success' ? '成功' : (row.http_status === 499 ? '断开' : '失败') }}
            </BaseBadge>
          </template>
          <template #cell-tokens="{ row }">
            <span class="usage-token">
              {{ row.prompt_tokens ?? 0 }}
              <span class="usage-token-sep">/</span>
              <span :class="{ 'usage-token-cache': (row.cache_read_tokens || 0) > 0 }">{{ row.cache_read_tokens ?? 0 }}</span>
              <span class="usage-token-sep">/</span>
              {{ row.completion_tokens ?? 0 }}
            </span>
            <BaseHint v-if="row.estimated" inline text="（估算）" />
          </template>
          <template #cell-attempt_count="{ row }">
            <span :class="{ 'usage-attempt-retry': (row.attempt_count || 1) > 1 }">{{ row.attempt_count || 1 }}</span>
          </template>
          <template #cell-duration_ms="{ row }">
            {{ row.duration_ms != null ? row.duration_ms + 'ms' : '—' }}
          </template>
          <template #cell-error_msg="{ row }">{{ row.error_msg || '—' }}</template>
        </DataTable>
      </ListPage>
    </ListPage>

    <RequestDetailDrawer v-model:visible="detailVisible" :log-id="detailLogId" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import {
  ListPage, DataTable, FilterBar, FilterField, ListToolbar,
  StatCard, TablePagination,
} from '@/components/list'
import type { DataColumn, StatTone } from '@/components/list'
import RequestDetailDrawer from '@/components/usage/RequestDetailDrawer.vue'
import { getUsageByKey, getUsageByUnit, getUsageLogs, getUsageByModel, getUsageSummary } from '@/api/usage'

const range = ref('today')
const loading = ref(false)
const summary = ref<any>({
  total: 0, total_tokens: 0, success_rate: null, active_keys: 0,
  filtered_count: 0, top_errors: [],
})
const byModel = ref<any[]>([])
const byKey = ref<any[]>([])
const byUnit = ref<any[]>([])

const logs = ref<any[]>([])
const logsLoading = ref(false)
const logPage = ref(1)
const logSize = ref(50)
const logTotal = ref(0)
const logStatus = ref('')
const logModel = ref('')
const logTableRef = ref<any>(null)

// ---------- 三张汇总表：各自分页 + 选中（CH-046） ----------
const modelPage = ref(1)
const modelSize = ref(20)
const unitPage = ref(1)
const unitSize = ref(20)
const keyPage = ref(1)
const keySize = ref(20)

function slicePage<T>(list: T[], page: number, size: number): T[] {
  const start = (page - 1) * size
  return list.slice(start, start + size)
}

// ---------- 三张汇总表的关键字筛选（CH-047） ----------
/** 各表独立的筛选关键字，互不干扰 */
const modelKeyword = ref('')
const unitKeyword = ref('')
const keyKeyword = ref('')

const filteredModel = computed(() => {
  const k = modelKeyword.value.trim().toLowerCase()
  if (!k) return byModel.value
  return byModel.value.filter((r: any) => String(r.model || '').toLowerCase().includes(k))
})
const filteredUnit = computed(() => {
  const k = unitKeyword.value.trim().toLowerCase()
  if (!k) return byUnit.value
  return byUnit.value.filter((r: any) =>
    String(r.upstream_name || r.upstream_id || '').toLowerCase().includes(k)
    || String(r.upstream_model || '').toLowerCase().includes(k),
  )
})
const filteredKey = computed(() => {
  const k = keyKeyword.value.trim().toLowerCase()
  if (!k) return byKey.value
  return byKey.value.filter((r: any) =>
    String(r.api_key_name || '').toLowerCase().includes(k)
    || String(r.api_key_id || '').includes(k),
  )
})

function resetModelFilter() {
  modelKeyword.value = ''
  modelPage.value = 1
}
function resetUnitFilter() {
  unitKeyword.value = ''
  unitPage.value = 1
}
function resetKeyFilter() {
  keyKeyword.value = ''
  keyPage.value = 1
}

const pagedByModel = computed(() => slicePage(filteredModel.value, modelPage.value, modelSize.value))
const pagedByUnit = computed(() => slicePage(filteredUnit.value, unitPage.value, unitSize.value))
const pagedByKey = computed(() => slicePage(filteredKey.value, keyPage.value, keySize.value))

/** 选中集合（按 row-key 存），跨页保持 */
const selectedModels = ref<string[]>([])
const selectedUnits = ref<string[]>([])
const selectedKeys = ref<string[]>([])
const selectedLogs = ref<(string | number)[]>([])

/** 全选/半选态：只作用于当前页 */
function pageState<T>(list: T[], page: number, size: number, selected: string[], keyOf: (r: T) => string) {
  const ids = slicePage(list, page, size).map(keyOf)
  const hit = ids.filter((k) => selected.includes(k)).length
  return {
    ids,
    all: ids.length > 0 && hit === ids.length,
    indeterminate: hit > 0 && hit < ids.length,
  }
}

function togglePage<T>(list: T[], page: number, size: number, selected: string[], keyOf: (r: T) => string, checked: boolean): string[] {
  const ids = slicePage(list, page, size).map(keyOf)
  if (checked) return [...new Set([...selected, ...ids])]
  const drop = new Set(ids)
  return selected.filter((k) => !drop.has(k))
}

const modelState = computed(() => pageState(filteredModel.value, modelPage.value, modelSize.value, selectedModels.value, (r: any) => r.model))
const unitState = computed(() => pageState(filteredUnit.value, unitPage.value, unitSize.value, selectedUnits.value, (r: any) => r.__k))
const keyState = computed(() => pageState(filteredKey.value, keyPage.value, keySize.value, selectedKeys.value, (r: any) => r.__k))
const logState = computed(() => pageState(logs.value, logPage.value, logSize.value, selectedLogs.value.map(String), (r: any) => String(r.id)))

const allModelChecked = computed(() => modelState.value.all)
const modelIndeterminate = computed(() => modelState.value.indeterminate)
const allUnitChecked = computed(() => unitState.value.all)
const unitIndeterminate = computed(() => unitState.value.indeterminate)
const allKeyChecked = computed(() => keyState.value.all)
const keyIndeterminate = computed(() => keyState.value.indeterminate)
const allLogChecked = computed(() => logState.value.all)
const logIndeterminate = computed(() => logState.value.indeterminate)

function toggleAllModels(v: boolean) {
  selectedModels.value = togglePage(filteredModel.value, modelPage.value, modelSize.value, selectedModels.value, (r: any) => r.model, v)
}
function toggleAllUnits(v: boolean) {
  selectedUnits.value = togglePage(filteredUnit.value, unitPage.value, unitSize.value, selectedUnits.value, (r: any) => r.__k, v)
}
function toggleAllKeys(v: boolean) {
  selectedKeys.value = togglePage(filteredKey.value, keyPage.value, keySize.value, selectedKeys.value, (r: any) => r.__k, v)
}

/**
 * 明细表是服务端分页，选中也要按当前页算。
 * 注意：这里只切「当前页已在数据里的行」，父组件清数组不会同步表格勾选态，
 * 所以必须显式调 DataTable 的 setSelection 补回。
 */
function toggleAllLogs(v: boolean) {
  const ids = logs.value.map((r: any) => String(r.id))
  if (v) {
    selectedLogs.value = [...new Set([...selectedLogs.value.map(String), ...ids])]
  } else {
    const drop = new Set(ids)
    selectedLogs.value = selectedLogs.value.map(String).filter((k) => !drop.has(k))
  }
  logTableRef.value?.setSelection?.(selectedLogs.value)
}

function clearLogSelection() {
  selectedLogs.value = []
  logTableRef.value?.clearSelection?.()
}

/** CH-038：请求详情抽屉 */
const detailVisible = ref(false)
const detailLogId = ref<number | null>(null)

function openDetail(row: any) {
  if (!row?.id) return
  detailLogId.value = row.id
  detailVisible.value = true
}

const rateTone = computed<StatTone>(() => {
  const r = summary.value.success_rate
  if (r === null) return 'default'
  if (r >= 0.99) return 'success'
  if (r >= 0.9) return 'warning'
  return 'danger'
})

const modelColumns: DataColumn[] = [
  { key: 'model', label: '模型', minWidth: 240 },
  { key: 'requests', label: '请求数', width: 100, sortable: true },
  { key: 'error_count', label: '错误数', width: 100 },
  { key: 'prompt_tokens', label: 'Prompt Tokens', width: 140, sortable: true },
  { key: 'completion_tokens', label: 'Completion', width: 130, sortable: true },
  { key: 'total_tokens', label: '总 Tokens', width: 130, sortable: true },
  { key: 'avg_duration_ms', label: '平均耗时', width: 110 },
  { key: 'upstream_count', label: '源数', width: 80 },
]

const unitColumns: DataColumn[] = [
  { key: 'upstream', label: '上游源', minWidth: 140 },
  { key: 'upstream_model', label: '真实模型名', minWidth: 220 },
  { key: 'requests', label: '请求数', width: 100, sortable: true },
  { key: 'error_count', label: '错误数', width: 100 },
  { key: 'total_tokens', label: '总 Tokens', width: 130, sortable: true },
  { key: 'request_models', label: '请求名数', width: 100 },
  { key: 'avg_duration_ms', label: '平均耗时', width: 110 },
]

const keyColumns: DataColumn[] = [
  { key: 'api_key_name', label: 'Key 名称', minWidth: 180 },
  { key: 'requests', label: '请求数', width: 110, sortable: true },
  { key: 'error_count', label: '错误数', width: 110 },
  { key: 'total_tokens', label: '总 Tokens', width: 140, sortable: true },
  { key: 'avg_duration_ms', label: '平均耗时', width: 120 },
]

const logColumns: DataColumn[] = [
  { key: 'created_at', label: '时间', width: 130 },
  { key: 'api_key_name', label: 'Key', minWidth: 110 },
  { key: 'model', label: '模型', minWidth: 180 },
  { key: 'upstream', label: '上游源', minWidth: 110 },
  { key: 'protocol', label: '协议', width: 100 },
  { key: 'status', label: '状态', width: 90 },
  { key: 'tokens', label: 'Tokens（输入/缓存/输出）', width: 170, ellipsis: false },
  { key: 'attempt_count', label: '尝试', width: 70 },
  { key: 'duration_ms', label: '耗时', width: 90 },
  { key: 'error_msg', label: '错误', minWidth: 160 },
]

/** 明细导出参数：带上当前的状态 / 模型筛选，导出「你看到的这批」 */
const logExportParams = computed<Record<string, string>>(() => {
  const p: Record<string, string> = { range: range.value }
  if (logStatus.value) p.status = logStatus.value
  if (logModel.value) p.model = logModel.value.trim()
  return p
})

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n ?? 0)
}

function formatTime(s: string): string {
  return (s || '').slice(5, 19).replace('T', ' ')
}

function resetLogFilters() {
  logStatus.value = ''
  logModel.value = ''
  logPage.value = 1
  loadLogs()
}

async function load() {
  loading.value = true
  try {
    const [s, m, k, u]: any = await Promise.all([
      getUsageSummary(range.value),
      getUsageByModel(range.value),
      getUsageByKey(range.value),
      getUsageByUnit(range.value),
    ])
    summary.value = s
    byModel.value = (m.models || []).map((r: any) => ({ ...r, __k: r.model }))
    byKey.value = (k.keys || []).map((r: any) => ({ ...r, __k: String(r.api_key_id) }))
    byUnit.value = (u.units || []).map((r: any) => ({
      ...r, __k: `${r.upstream_id}|${r.upstream_model}`,
    }))
  } finally {
    loading.value = false
  }
  loadLogs()
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const res: any = await getUsageLogs({
      range: range.value,
      page: logPage.value,
      size: logSize.value,
      status: logStatus.value || undefined,
      model: logModel.value || undefined,
    })
    logs.value = res.items || []
    logTotal.value = res.total || 0
  } finally {
    logsLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.usage-stat-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}

.usage-error-top {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.usage-error-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.usage-sub-title {
  margin: 20px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.usage-code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  background: var(--bg-elevated);
  padding: 1px 6px;
  border-radius: 4px;
}

.usage-error {
  color: var(--accent-red);
}

.usage-token {
  font-variant-numeric: tabular-nums;
}

.usage-token-sep {
  color: var(--text-tertiary);
  margin: 0 2px;
}

.usage-token-cache {
  color: var(--accent-green);
}

.usage-attempt-retry {
  color: var(--accent-amber);
  font-weight: 600;
}

@media (max-width: 1200px) {
  .usage-stat-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .usage-stat-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
