<template>
  <div>
    <BaseSection variant="card" title="用量统计">
      <template #actions>
        <el-radio-group v-model="range" size="small" @change="load">
          <el-radio-button value="today">今日</el-radio-button>
          <el-radio-button value="7d">近 7 天</el-radio-button>
          <el-radio-button value="30d">近 30 天</el-radio-button>
        </el-radio-group>
        <BaseButton variant="ghost" size="sm" style="margin-left: 8px" @click="load">刷新</BaseButton>
      </template>

      <!-- 汇总卡片 -->
      <el-row :gutter="16" style="margin-bottom: 16px">
        <el-col :span="6">
          <BaseCard variant="hoverable">
            <div class="metric-label">请求总数</div>
            <div class="metric-value">{{ summary.total }}</div>
          </BaseCard>
        </el-col>
        <el-col :span="6">
          <BaseCard variant="hoverable">
            <div class="metric-label">总 Tokens</div>
            <div class="metric-value">{{ formatTokens(summary.total_tokens) }}</div>
          </BaseCard>
        </el-col>
        <el-col :span="6">
          <BaseCard variant="hoverable">
            <div class="metric-label">成功率</div>
            <div class="metric-value" :style="{ color: rateColor }">{{ summary.success_rate === null ? '—' : (summary.success_rate * 100).toFixed(1) + '%' }}</div>
          </BaseCard>
        </el-col>
        <el-col :span="6">
          <BaseCard variant="hoverable">
            <div class="metric-label">活跃 Key</div>
            <div class="metric-value">{{ summary.active_keys }}</div>
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
        <el-text type="info" size="small">— 号池积分消耗核算，聚合请求会落到真实模型名</el-text>
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
      <div v-if="!byUnit.length" class="empty-tip">
        <el-text type="info" size="small">暂无数据。该统计需要请求实际命中上游后才会有记录。</el-text>
      </div>

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
      <h4 style="margin: 16px 0 8px">最近请求明细</h4>
      <div class="log-filters">
        <el-select v-model="logStatus" size="small" style="width: 110px" @change="loadLogs">
          <el-option label="全部状态" value="" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="error" />
        </el-select>
        <el-input v-model="logModel" size="small" placeholder="按模型名过滤…" style="width: 220px" clearable @change="loadLogs" />
      </div>
      <el-table :data="logs" stripe size="small" v-loading="logsLoading">
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
            <BaseBadge :variant="row.status === 'success' ? 'green' : 'red'">{{ row.status === 'success' ? '成功' : '失败' }}</BaseBadge>
          </template>
        </el-table-column>
        <el-table-column label="Tokens" width="110">
          <template #default="{ row }">
            {{ row.total_tokens }}<el-text v-if="row.estimated" type="info" size="small">（估算）</el-text>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ row.duration_ms != null ? row.duration_ms + 'ms' : '—' }}</template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_msg || '—' }}</template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="logPage"
          :page-size="logSize"
          :total="logTotal"
          layout="prev, pager, next, total"
          size="small"
          @current-change="loadLogs"
        />
      </div>
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
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
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
