<template>
  <div>
    <el-alert type="info" :closable="false" style="margin-bottom: 16px"
      title="这里是智能路由的运行观测：模型探测延迟、规则候选可用率与故障冷却状态。修改参数请到「路由参数」。" />

    <!-- 汇总卡片 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6">
        <BaseCard variant="hoverable">
          <div class="metric-label">探测单元</div>
          <div class="metric-value">{{ summary.total }}</div>
          <div class="metric-sub">模型 × 上游源</div>
        </BaseCard>
      </el-col>
      <el-col :span="6">
        <BaseCard variant="hoverable">
          <div class="metric-label">可用</div>
          <div class="metric-value" style="color: var(--accent-green)">{{ summary.ok }}</div>
        </BaseCard>
      </el-col>
      <el-col :span="6">
        <BaseCard variant="hoverable">
          <div class="metric-label">不可用</div>
          <div class="metric-value" style="color: var(--accent-red)">{{ summary.down }}</div>
        </BaseCard>
      </el-col>
      <el-col :span="6">
        <BaseCard variant="hoverable">
          <div class="metric-label">最快候选</div>
          <div class="metric-value" style="font-size: 1.1rem">
            {{ fastest ? fastest.model : 'N/A' }}
          </div>
          <div class="metric-sub">{{ fastest ? `${fastest.latency}s` : '暂无数据' }}</div>
        </BaseCard>
      </el-col>
    </el-row>

    <!-- 故障与冷却 -->
    <BaseSection variant="card" title="模型故障 / 冷却状态">
      <div v-if="failList.length" class="fail-list">
        <div v-for="f in failList" :key="f.model" class="fail-item">
          <BaseBadge :variant="f.kind === 'probe' || f.remaining > 0 ? 'red' : 'green'">
            {{ f.kind === 'probe' || f.remaining > 0 ? '故障' : '已恢复' }}
          </BaseBadge>
          <span class="fail-model">{{ f.model }}</span>
          <span class="fail-desc">
            <template v-if="f.kind === 'probe'">— 探测不可用{{ f.err ? `：${f.err}` : '' }}</template>
            <template v-else-if="f.remaining > 0">— 连续失败 {{ f.fails }} 次，冷却剩余 {{ f.remaining }}s</template>
            <template v-else>— 失败 {{ f.fails }} 次</template>
          </span>
        </div>
      </div>
      <div v-else class="empty-tip">所有模型正常运行，无故障记录</div>
    </BaseSection>

    <!-- 延迟状态 -->
    <BaseSection variant="card" title="模型延迟状态">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="load">刷新</BaseButton>
      </template>

      <el-table :data="latencyRows" stripe v-loading="loading">
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <BaseBadge :variant="row.status === 'ok' ? 'green' : row.status === 'down' ? 'red' : 'gray'">
              {{ row.status === 'ok' ? '可用' : row.status === 'down' ? '不可用' : '未知' }}
            </BaseBadge>
          </template>
        </el-table-column>
        <el-table-column prop="upstream" label="上游源" width="130" />
        <el-table-column prop="model" label="模型" min-width="260" />
        <el-table-column prop="latency" label="延迟" width="100" />
        <el-table-column prop="error" label="错误" min-width="160">
          <template #default="{ row }">{{ row.error || '-' }}</template>
        </el-table-column>
      </el-table>
    </BaseSection>

    <!-- 规则状态 -->
    <BaseSection variant="card" title="路由规则详细状态">
      <div v-for="rule in rulesStatus" :key="rule.name" style="margin-bottom: 16px">
        <h4 style="margin: 0 0 8px">
          规则: {{ rule.name }}
          <el-text type="info" size="small">
            候选 {{ rule.candidates.length }} · 可用 {{ rule.candidates.filter((c: any) => c.status === 'ok').length }}
          </el-text>
        </h4>
        <el-table :data="rule.candidates" size="small" border>
          <el-table-column prop="model" label="模型" min-width="240" />
          <el-table-column prop="upstream" label="上游源" width="110" />
          <el-table-column prop="base_weight" label="基础权重" width="90" />
          <el-table-column prop="dynamic_weight" label="动态权重" width="90" />
          <el-table-column prop="latency" label="延迟" width="90">
            <template #default="{ row }">{{ row.latency ?? 'N/A' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <BaseBadge :variant="row.status === 'ok' ? 'green' : row.status === 'down' ? 'red' : 'gray'">
                {{ row.status }}
              </BaseBadge>
            </template>
          </el-table-column>
          <el-table-column prop="max_context" label="上下文" width="110" />
          <el-table-column prop="max_output" label="输出" width="100" />
        </el-table>
      </div>
      <div v-if="!rulesStatus.length" class="empty-tip">暂无路由规则，可到「路由规则」页添加</div>
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { getDashboard, getStatus } from '@/api/common'

const loading = ref(false)
const latencyPanel = ref<Record<string, any>>({})
const rulesStatus = ref<any[]>([])
const health = ref<any>({ fails: {}, cooldown: {}, probe_down: {} })

// 探测 key 形如 "upstream:model"，拆分展示
const latencyRows = computed(() =>
  Object.entries(latencyPanel.value).map(([key, info]: [string, any]) => {
    const idx = key.indexOf(':')
    const upstream = idx > 0 ? key.slice(0, idx) : '-'
    const model = idx > 0 ? key.slice(idx + 1) : key
    return { key, upstream, model, latency: info.latency, status: info.status, error: info.error }
  })
)

const summary = computed(() => {
  let ok = 0
  let down = 0
  Object.values(latencyPanel.value).forEach((info: any) => {
    if (info.status === 'ok') ok++
    else if (info.status === 'down') down++
  })
  return { total: Object.keys(latencyPanel.value).length, ok, down }
})

const fastest = computed(() => {
  // 面板返回的 latency 是 "1.2s" 字符串，统一转数值比较
  let best: { model: string; latency: number } | null = null
  for (const row of latencyRows.value) {
    const num = typeof row.latency === 'number'
      ? row.latency
      : parseFloat(String(row.latency ?? ''))
    if (row.status === 'ok' && Number.isFinite(num)) {
      if (!best || num < best.latency) best = { model: row.model, latency: num }
    }
  }
  return best
})

const failList = computed(() => {
  const fails = health.value.fails || {}
  const cooldown = health.value.cooldown || {}
  const probeDown = health.value.probe_down || {}
  const list: any[] = Object.entries(fails).map(([model, count]) => ({
    model,
    fails: count,
    remaining: cooldown[model] || 0,
    kind: 'forward',
  }))
  Object.entries(probeDown).forEach(([model, err]) => {
    if (!list.some((x) => x.model === model)) {
      list.push({ model, fails: 0, remaining: 0, kind: 'probe', err: String(err) })
    }
  })
  return list
})

async function load() {
  loading.value = true
  try {
    const [res, dash]: any = await Promise.all([getStatus(), getDashboard()])
    latencyPanel.value = res.latency_panel || {}
    rulesStatus.value = res.rules || []
    health.value = (dash && dash.health) || res.health || {}
  } finally {
    loading.value = false
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
.metric-sub {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 2px;
}
.fail-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 13px;
}
.fail-model {
  font-weight: 600;
}
.fail-desc {
  color: var(--text-tertiary);
}
.empty-tip {
  color: var(--text-tertiary);
  font-size: 13px;
  padding: 12px 0;
}
</style>
