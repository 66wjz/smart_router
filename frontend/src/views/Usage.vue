<template>
  <div>
    <BaseSection variant="card" title="用量统计">
      <template #actions>
        <el-radio-group v-model="range" size="small" @change="load">
          <el-radio-button value="today">今日</el-radio-button>
          <el-radio-button value="7d">近 7 天</el-radio-button>
          <el-radio-button value="30d">近 30 天</el-radio-button>
        </el-radio-group>
        <BaseButton variant="ghost" size="sm" @click="load">刷新</BaseButton>
      </template>

      <!-- 汇总卡片 -->
      <el-row :gutter="16" style="margin-bottom: 16px">
        <el-col :span="5">
          <BaseCard variant="hoverable">
            <div class="metric-label">请求总数</div>
            <div class="metric-value">{{ summary.total }}</div>
          </BaseCard>
        </el-col>
        <el-col :span="5">
          <BaseCard variant="hoverable">
            <div class="metric-label">总 Tokens</div>
            <div class="metric-value">{{ formatTokens(summary.total_tokens) }}</div>
          </BaseCard>
        </el-col>
        <el-col :span="5">
          <BaseCard variant="hoverable">
            <div class="metric-label">成功率</div>
            <div class="metric-value" :style="{ color: rateColor }">{{ summary.success_rate === null ? '—' : (summary.success_rate * 100).toFixed(1) + '%' }}</div>
          </BaseCard>
        </el-col>
        <el-col :span="5">
          <BaseCard variant="hoverable">
            <div class="metric-label">活跃 Key</div>
            <div class="metric-value">{{ summary.active_keys }}</div>
          </BaseCard>
        </el-col>
        <!-- CH-041：被请求过滤引擎拦截的请求（未发往任何上游，不消耗号池） -->
        <el-col :span="4">
          <BaseCard variant="hoverable">
            <div class="metric-label">
              已过滤
              <el-tooltip content="命中过滤规则、未发往上游的请求。这些请求不消耗号池额度，也不会计入上游违规。" placement="top">
                <span class="fe-tip">?</span>
              </el-tooltip>
            </div>
            <div class="metric-value" :style="summary.filtered_count ? 'color: var(--accent-amber)' : ''">{{ summary.filtered_count || 0 }}</div>
          </BaseCard>
        </el-col>
      </el-row>

      <!-- 错误 Top -->
      <div v-if="summary.top_errors?.length" class="error-top">
        <span class="error-top-title">高频错误：</span>
        <el-tag v-for="e in summary.top_errors" :key="e.target" type="danger" size="small" style="margin-right: 8px">
          {{ e.target }} × {{ e.count }}
        </el-tag>
      </div>

      <!-- 按模型 -->
      <h4 style="margin: 16px 0 8px">按模型</h4>
      <el-table :data="byModel" stripe size="small" v-loading="loading">
        <el-table-column prop="model" label="模型" min-width="240" show-overflow-tooltip />
        <el-table-column prop="requests" label="请求数" width="90" sortable />
        <el-table-column label="错误数" width="90">
          <template #default="{ row }">
            <span :style="row.error_count ? 'color: var(--accent-red)' : ''">{{ row.error_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="prompt_tokens" label="Prompt Tokens" width="130" sortable />
        <el-table-column prop="completion_tokens" label="Completion" width="120" sortable />
        <el-table-column prop="total_tokens" label="总 Tokens" width="120" sortable />
        <el-table-column prop="avg_duration_ms" label="平均耗时" width="100">
          <template #default="{ row }">{{ row.avg_duration_ms ? row.avg_duration_ms + 'ms' : '—' }}</template>
        </el-table-column>
        <el-table-column prop="upstream_count" label="源数" width="70" />
      </el-table>

      <!-- 按单元（上游源 × 真实模型） -->
      <h4 style="margin: 16px 0 8px">
        按单元（上游源 × 真实模型）
        <BaseHint inline text="— 号池积分消耗核算，聚合请求会落到真实模型名" />
      </h4>
      <el-table :data="byUnit" stripe size="small" v-loading="loading">
        <el-table-column label="上游源" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.upstream_name || row.upstream_id }}</template>
        </el-table-column>
        <el-table-column prop="upstream_model" label="真实模型名" min-width="220" show-overflow-tooltip />
        <el-table-column prop="requests" label="请求数" width="90" sortable />
        <el-table-column label="错误数" width="90">
          <template #default="{ row }">
            <span :style="row.error_count ? 'color: var(--accent-red)' : ''">{{ row.error_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="总 Tokens" width="120" sortable>
          <template #default="{ row }">{{ formatTokens(row.total_tokens) }}</template>
        </el-table-column>
        <el-table-column label="请求名数" width="90">
          <template #default="{ row }">{{ row.request_models }}</template>
        </el-table-column>
        <el-table-column prop="avg_duration_ms" label="平均耗时" width="100">
          <template #default="{ row }">{{ row.avg_duration_ms ? row.avg_duration_ms + 'ms' : '—' }}</template>
        </el-table-column>
      </el-table>
      <BaseEmptyState v-if="!byUnit.length" description="暂无数据。该统计需要请求实际命中上游后才会有记录。" />

      <!-- 按 Key -->
      <h4 style="margin: 16px 0 8px">按 API Key</h4>
      <el-table :data="byKey" stripe size="small" v-loading="loading">
        <el-table-column label="Key 名称" min-width="180">
          <template #default="{ row }">{{ row.api_key_name || `#${row.api_key_id}` }}</template>
        </el-table-column>
        <el-table-column prop="requests" label="请求数" width="100" sortable />
        <el-table-column label="错误数" width="100">
          <template #default="{ row }">
            <span :style="row.error_count ? 'color: var(--accent-red)' : ''">{{ row.error_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="总 Tokens" width="130" sortable />
        <el-table-column prop="avg_duration_ms" label="平均耗时" width="110">
          <template #default="{ row }">{{ row.avg_duration_ms ? row.avg_duration_ms + 'ms' : '—' }}</template>
        </el-table-column>
      </el-table>

      <!-- 明细 -->
      <h4 style="margin: 16px 0 8px">
        最近请求明细
        <BaseHint inline text="— 点击任意一行查看原始请求 / 实际转发 / 上游响应 三栏对比" />
      </h4>
      <div class="log-filters">
        <el-select v-model="logStatus" size="small" style="width: 110px" @change="loadLogs">
          <el-option label="全部状态" value="" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="error" />
          <el-option label="已过滤" value="filtered" />
        </el-select>
        <el-input v-model="logModel" size="small" placeholder="按模型名过滤…" style="width: 220px" clearable @change="loadLogs" />
      </div>
      <el-table :data="logs" stripe size="small" v-loading="logsLoading"
        row-class-name="log-row-clickable" @row-click="openDetail">
        <el-table-column label="时间" width="100">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="Key" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.api_key_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="model" label="模型" min-width="180" show-overflow-tooltip />
        <el-table-column label="上游源" min-width="110">
          <template #default="{ row }">{{ row.upstream_name || row.upstream_id || '—' }}</template>
        </el-table-column>
        <el-table-column label="协议" width="90">
          <template #default="{ row }">
            <BaseBadge variant="gray">{{ row.protocol }}{{ row.stream ? ' ·流式' : '' }}</BaseBadge>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <!-- CH-041：被过滤引擎拦截（未发往上游），与普通失败区分开 -->
            <BaseBadge
              v-if="(row.error_msg || '').startsWith('【已过滤】')"
              variant="amber"
            >已过滤</BaseBadge>
            <BaseBadge v-else :variant="row.status === 'success' ? 'green' : (row.http_status === 499 ? 'amber' : 'red')">
              {{ row.status === 'success' ? '成功' : (row.http_status === 499 ? '断开' : '失败') }}
            </BaseBadge>
          </template>
        </el-table-column>
        <el-table-column label="Tokens（输入/缓存/输出）" width="170">
          <template #default="{ row }">
            <span class="token-cell">
              {{ row.prompt_tokens ?? 0 }}
              <span class="token-sep">/</span>
              <span :class="{ 'token-cache': (row.cache_read_tokens || 0) > 0 }">{{ row.cache_read_tokens ?? 0 }}</span>
              <span class="token-sep">/</span>
              {{ row.completion_tokens ?? 0 }}
            </span>
            <BaseHint v-if="row.estimated" inline text="（估算）" />
          </template>
        </el-table-column>
        <el-table-column label="尝试" width="70">
          <template #default="{ row }">
            <span :class="{ 'attempt-retry': (row.attempt_count || 1) > 1 }">{{ row.attempt_count || 1 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ row.duration_ms != null ? row.duration_ms + 'ms' : '—' }}</template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_msg || '—' }}</template>
        </el-table-column>
      </el-table>
      <BasePagination
        :page="logPage"
        :page-size="logSize"
        :total="logTotal"
        @update:page="logPage = $event"
        @change="loadLogs"
      />
    </BaseSection>

    <RequestDetailDrawer v-model:visible="detailVisible" :log-id="detailLogId" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BasePagination from '@/components/base/BasePagination.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import RequestDetailDrawer from '@/components/usage/RequestDetailDrawer.vue'
import { getUsageByKey, getUsageByUnit, getUsageLogs, getUsageByModel, getUsageSummary } from '@/api/usage'

const range = ref('today')
const loading = ref(false)
const summary = ref<any>({ total: 0, total_tokens: 0, success_rate: null, active_keys: 0, top_errors: [] })
const byModel = ref<any[]>([])
const byKey = ref<any[]>([])
const byUnit = ref<any[]>([])

const logs = ref<any[]>([])
const logsLoading = ref(false)
const logPage = ref(1)
const logSize = 50
const logTotal = ref(0)
const logStatus = ref('')
const logModel = ref('')

/** CH-038：请求详情抽屉 */
const detailVisible = ref(false)
const detailLogId = ref<number | null>(null)

function openDetail(row: any) {
  if (!row?.id) return
  detailLogId.value = row.id
  detailVisible.value = true
}

const rateColor = computed(() => {
  const r = summary.value.success_rate
  if (r === null) return 'var(--text-primary)'
  if (r >= 0.99) return 'var(--accent-green)'
  if (r >= 0.9) return 'var(--accent-amber)'
  return 'var(--accent-red)'
})

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n ?? 0)
}

function formatTime(s: string): string {
  return (s || '').slice(5, 19).replace('T', ' ')
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
    byModel.value = m.models || []
    byKey.value = k.keys || []
    byUnit.value = u.units || []
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
      size: logSize,
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
.metric-label {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}
.metric-value {
  font-size: 1.6rem;
  font-weight: 700;
  margin-top: 4px;
}
/* CH-041：已过滤卡片的说明图标 */
.fe-tip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--fill-light, #f2f3f5);
  color: var(--text-tertiary);
  font-size: 10px;
  cursor: help;
  margin-left: 4px;
  vertical-align: middle;
}
.error-top {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.error-top-title {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}
.log-filters {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.token-cell {
  font-variant-numeric: tabular-nums;
}
.token-sep {
  color: var(--text-tertiary);
  margin: 0 2px;
}
.token-cache {
  color: var(--accent-green);
}
.attempt-retry {
  color: var(--accent-amber);
  font-weight: 600;
}
:deep(.log-row-clickable) {
  cursor: pointer;
}
</style>
