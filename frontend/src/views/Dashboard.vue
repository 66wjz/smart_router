<template>
  <div>
    <!-- 指标卡片：中转视角 ×2 + 路由视角 ×2 -->
    <div class="metric-grid">
      <BaseCard v-for="m in metrics" :key="m.label" variant="hoverable">
        <div class="metric-label">
          <span class="func-tag" :class="m.tagClass">{{ m.tag }}</span>{{ m.label }}
        </div>
        <div class="metric-value" :style="{ color: m.color }">{{ m.value }}</div>
        <div v-if="m.sub" class="metric-sub">{{ m.sub }}</div>
      </BaseCard>
    </div>

    <!-- 上游源状态一览 + 智能路由概览（同行等高） -->
    <div class="dashboard-row row-wide-left">
      <BaseSection title="上游源状态一览" variant="card" class="fill-card">
        <el-table :data="upstreams" size="small">
          <el-table-column prop="name" label="上游源" min-width="110" />
          <el-table-column label="分组" min-width="130">
            <template #default="{ row }">
              <BaseBadge v-for="g in row._groups" :key="g" :variant="g === 'free' ? 'blue' : 'amber'" class="grp-badge">{{ g }}</BaseBadge>
            </template>
          </el-table-column>
          <el-table-column label="模型" width="60">
            <template #default="{ row }">{{ (row.models || []).length }}</template>
          </el-table-column>
          <el-table-column label="Key" width="60">
            <template #default="{ row }">{{ (row.keys || []).length }}</template>
          </el-table-column>
          <el-table-column label="智能重试" width="80">
            <template #default="{ row }">
              <BaseBadge v-if="row.smart_retry" variant="purple">开</BaseBadge><span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <BaseBadge :variant="row.enabled ? 'green' : 'gray'">{{ row.enabled ? '启用' : '禁用' }}</BaseBadge>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!upstreams.length" class="empty-tip">暂无上游源</div>
      </BaseSection>

      <BaseSection title="智能路由概览" variant="card" class="fill-card">
        <div v-for="r in ruleSummaries" :key="r.name" class="rule-item">
          <div class="rule-name">{{ r.name }}</div>
          <div class="rule-meta">
            候选 {{ r.total }} · 可用 {{ r.available }}
            <template v-if="r.fastest">
              · 最快 <span class="latency-ok">{{ r.fastest.latency }}s</span>（{{ r.fastest.model }}）
            </template>
          </div>
        </div>
        <div v-if="!ruleSummaries.length" class="empty-tip">暂无路由规则</div>
        <div v-if="aggNames.length" class="agg-chips">
          <div class="rule-meta" style="margin-bottom: 4px">聚合入口：</div>
          <span v-for="n in aggNames" :key="n" class="chip">{{ n }}</span>
        </div>
      </BaseSection>
    </div>

    <!-- 故障状态 + 快速操作（同行等高） -->
    <div class="dashboard-row row-wide-left">
      <BaseSection title="模型故障状态" variant="card" class="fill-card">
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

      <BaseSection title="快速操作" variant="card" class="fill-card">
        <div class="quick-actions">
          <BaseButton variant="primary" block :disabled="reloading" @click="handleReload">
            <BaseIcon name="refresh-cw" :size="14" />
            热重载配置
          </BaseButton>
          <BaseButton variant="ghost" block @click="loadAll">
            <BaseIcon name="activity" :size="14" />
            刷新延迟数据
          </BaseButton>
          <BaseButton variant="ghost" block @click="router.push('/settings')">
            <BaseIcon name="collection" :size="14" />
            分组管理
          </BaseButton>
        </div>
      </BaseSection>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { getDashboard, getStatus, reloadConfig } from '@/api/common'
import { listUpstreams } from '@/api/upstreams'
import { listApiKeys } from '@/api/apiKeys'
import { getAggregatedNames } from '@/api/aggregated'

const router = useRouter()

const dashboard = reactive({
  upstream_count: 0,
  model_count: 0,
  model_ok: 0,
  model_down: 0,
  rule_count: 0,
  pointer_count: 0,
  api_key_count: 0,
  health: { fails: {} as Record<string, number>, cooldown: {} as Record<string, number> },
})

const upstreams = ref<any[]>([])
const apiKeys = ref<any[]>([])
const aggNames = ref<string[]>([])
const statusData = ref<any>({})
const reloading = ref(false)

const rate = computed(() => {
  const total = dashboard.model_ok + dashboard.model_down
  if (total <= 0) return 'N/A'
  return `${Math.round((dashboard.model_ok / total) * 100)}%`
})

const rateColor = computed(() => {
  const total = dashboard.model_ok + dashboard.model_down
  if (total <= 0) return '#888'
  return dashboard.model_ok / total >= 0.7 ? '#00b42a' : '#ff7d00'
})

const enabledUpstreamCount = computed(() => upstreams.value.filter((u) => u.enabled).length)
const totalModelCount = computed(() => upstreams.value.reduce((s, u) => s + (u.models || []).length, 0))
const totalKeyCount = computed(() => upstreams.value.reduce((s, u) => s + (u.keys || []).length, 0))
const keyGroupCoverage = computed(() => {
  const gs = new Set<string>()
  for (const k of apiKeys.value) for (const g of k.groups || []) gs.add(g)
  return [...gs].join(' / ') || '—'
})

const fastestOverall = computed(() => {
  const panel = statusData.value.latency_panel || {}
  let best: { model: string; latency: number } | null = null
  for (const [model, info] of Object.entries<any>(panel)) {
    if (info?.status === 'ok' && typeof info.latency === 'number') {
      if (!best || info.latency < best.latency) best = { model, latency: info.latency }
    }
  }
  return best
})

const metrics = computed(() => [
  {
    tag: '中转', tagClass: 'tag-relay', label: '上游源',
    value: `${enabledUpstreamCount.value} 启用`,
    sub: `共 ${upstreams.value.length} 个 · 已配置模型 ${totalModelCount.value} 个 · ${totalKeyCount.value} 把上游 Key`,
    color: 'var(--text-primary)',
  },
  {
    tag: '中转', tagClass: 'tag-relay', label: 'API Key',
    value: String(dashboard.api_key_count),
    sub: `覆盖分组：${keyGroupCoverage.value}`,
    color: 'var(--text-primary)',
  },
  {
    tag: '路由', tagClass: 'tag-route', label: '候选可用率',
    value: rate.value,
    sub: `${dashboard.model_ok} 可用 / ${dashboard.model_down} 不可用（探测）`,
    color: rateColor.value,
  },
  {
    tag: '路由', tagClass: 'tag-route', label: '最快候选',
    value: fastestOverall.value ? fastestOverall.value.model.split('/').pop() : 'N/A',
    sub: fastestOverall.value ? `当前延迟 ${fastestOverall.value.latency}s` : '暂无探测数据',
    color: 'var(--text-primary)',
  },
])

const ruleSummaries = computed(() => {
  const rules = statusData.value.rules || []
  return rules.map((r: any) => {
    const cands = r.candidates || []
    const latOk = cands
      .filter((c: any) => c.status === 'ok' && typeof c.latency === 'number')
      .sort((a: any, b: any) => a.latency - b.latency)
    const available = cands.filter((c: any) => c.status === 'ok' || c.available).length
    return {
      name: r.name,
      total: cands.length,
      available: available || latOk.length,
      fastest: latOk.length ? { model: String(latOk[0].model).split('/').pop(), latency: latOk[0].latency } : null,
    }
  })
})

const failList = computed(() => {
  const h = dashboard.health || {}
  const fails = (h as any).fails || {}
  const cooldown = (h as any).cooldown || {}
  const probeDown = (h as any).probe_down || {}
  const list: any[] = Object.entries(fails).map(([model, count]) => ({
    model,
    fails: count,
    remaining: (cooldown as any)[model] || 0,
    kind: 'forward',
  }))
  Object.entries(probeDown).forEach(([model, err]) => {
    if (!list.some((x) => x.model === model)) {
      list.push({ model, fails: 0, remaining: 0, kind: 'probe', err: String(err) })
    }
  })
  return list
})

async function loadAll() {
  const [dash, ups, keys, aggs, status]: any[] = await Promise.all([
    getDashboard(),
    listUpstreams(),
    listApiKeys(),
    getAggregatedNames(),
    getStatus(),
  ])
  Object.assign(dashboard, dash)
  upstreams.value = (ups.upstreams || []).map((u: any) => ({
    ...u,
    _groups: u.groups && u.groups.length ? u.groups : [u.group || 'free'],
  }))
  apiKeys.value = keys.api_keys || []
  aggNames.value = aggs.aggregated_names || aggs.names || []
  statusData.value = status
}

async function handleReload() {
  reloading.value = true
  try {
    await reloadConfig()
    ElMessage.success('配置已热重载')
    loadAll()
  } finally {
    reloading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.metric-label {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.func-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.tag-relay { background: #ecf5ff; color: #409eff; }
.tag-route { background: #f0f9eb; color: #67c23a; }

.metric-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}

.metric-sub {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.dashboard-row {
  display: grid;
  gap: 16px;
  margin-bottom: 16px;
  align-items: stretch;
}

.row-wide-left { grid-template-columns: 3fr 2fr; }

.fill-card { height: 100%; margin-bottom: 0; padding-top: 20px; }

.fill-card::before { display: none; }

.grp-badge { margin-right: 4px; }

.muted { color: var(--text-tertiary); }

.rule-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-light, #f2f3f5);
  font-size: 13px;
}

.rule-item:last-of-type { border-bottom: none; }

.rule-name { font-weight: 600; margin-bottom: 4px; }

.rule-meta { color: var(--text-tertiary); font-size: 12px; }

.latency-ok { color: #00b42a; font-weight: 600; }

.agg-chips { margin-top: 10px; }

.chip {
  display: inline-block;
  background: var(--bg-secondary, #f4f4f5);
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 12px;
  margin: 0 6px 6px 0;
  font-family: monospace;
}

.fail-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 13px;
}

.fail-model { font-weight: 600; }

.fail-desc { color: var(--text-tertiary); }

.empty-tip {
  color: var(--text-tertiary);
  font-size: 13px;
  padding: 12px 0;
}

.quick-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 1024px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .dashboard-row { grid-template-columns: 1fr; }
}
</style>
