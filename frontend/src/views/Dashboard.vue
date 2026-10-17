<template>
  <div class="dash">
    <!-- ① 健康条 -->
    <div class="health-bar" :class="{ 'is-warn': attention.length > 0 }">
      <div class="hb-item">
        <span class="hb-dot" :class="probeSummary.enabled ? 'on' : 'off'"></span>
        <span class="hb-label">探测</span>
        <span class="hb-value">
          {{ probeSummary.enabled ? '开' : '关' }} · {{ probeSummary.global_interval }}s
        </span>
      </div>
      <span class="hb-sep"></span>
      <div class="hb-item">
        <span class="hb-label">单元</span>
        <span class="hb-value">{{ probeSummary.unit_count }}</span>
        <span class="hb-sub">
          可用 {{ probeSummary.ok }} / 不可用 {{ probeSummary.down }} / 未知 {{ probeSummary.unknown }}
        </span>
      </div>
      <span class="hb-sep"></span>
      <div class="hb-item">
        <span class="hb-label">探测时段</span>
        <span class="hb-value">{{ probeSummary.global_schedule }}</span>
        <span v-if="probeSummary.scheduled_off" class="hb-sub">当前 {{ probeSummary.scheduled_off }} 个单元在时段外</span>
      </div>
      <span class="hb-sep"></span>
      <div class="hb-item">
        <span class="hb-label">7 天成功率</span>
        <span class="hb-value" :style="{ color: rateColor }">{{ formatRate(usage7d.success_rate) }}</span>
      </div>
      <span class="hb-sep"></span>
      <div class="hb-item">
        <span class="hb-label">待关注</span>
        <span class="hb-value" :style="{ color: attention.length ? 'var(--accent-red)' : 'var(--accent-green)' }">
          {{ attention.length }}
        </span>
      </div>
      <div class="hb-actions">
        <BaseButton variant="ghost" size="sm" @click="loadAll">刷新</BaseButton>
      </div>
    </div>

    <!-- ② 五张指标卡 -->
    <div class="metric-grid">
      <div v-for="m in metrics" :key="m.label" class="metric-card" @click="m.to && router.push(m.to)">
        <div class="mc-label">{{ m.label }}</div>
        <div class="mc-value">
          {{ m.value }}
          <span v-if="m.delta !== null && m.delta !== undefined" class="mc-delta" :class="m.delta >= 0 ? 'up' : 'down'">
            {{ m.delta >= 0 ? '↑' : '↓' }}{{ Math.abs(m.delta * 100).toFixed(0) }}%
          </span>
        </div>
        <div class="mc-sub">{{ m.sub }}</div>
      </div>
    </div>

    <!-- ③ 趋势 + 贡献占比 -->
    <div class="two-col">
      <BaseSection variant="card" title="近 7 天用量趋势">
        <template #actions>
          <div class="legend">
            <span class="lg-item"><i class="lg-dot" style="background:#4f8cff"></i>请求数</span>
            <span class="lg-item"><i class="lg-dot" style="background:#8f6cff"></i>Tokens</span>
          </div>
        </template>
        <div v-if="hasTrend" class="chart-wrap">
          <svg :viewBox="`0 0 ${CHART_W} ${CHART_H}`" preserveAspectRatio="none"
               :width="CHART_W" :height="CHART_H"
               :style="{ width: '100%', height: '180px' }" class="trend-svg">
            <defs>
              <linearGradient id="gReq" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#4f8cff" stop-opacity="0.26" />
                <stop offset="100%" stop-color="#4f8cff" stop-opacity="0" />
              </linearGradient>
            </defs>
            <!-- 网格线 -->
            <line v-for="g in 4" :key="'g' + g" :x1="PAD_L" :x2="CHART_W - PAD_R"
                  :y1="gridY(g)" :y2="gridY(g)" class="grid-line" />
            <!-- 请求数面积 + 折线 -->
            <polygon :points="reqArea" fill="url(#gReq)" />
            <polyline :points="reqLine" fill="none" stroke="#4f8cff" stroke-width="2" stroke-linejoin="round" />
            <!-- Tokens 折线（虚线） -->
            <polyline :points="tokLine" fill="none" stroke="#8f6cff" stroke-width="2"
                      stroke-dasharray="4 3" stroke-linejoin="round" opacity="0.85" />
            <!-- 数据点 + 原生 tooltip -->
            <g v-for="(p, i) in points" :key="'p' + i">
              <circle :cx="p.x" :cy="p.ry" r="3.2" fill="#4f8cff" />
              <circle :cx="p.x" :cy="p.ty" r="2.6" fill="#8f6cff" />
              <rect :x="p.x - 22" :y="0" width="44" height="26" fill="transparent">
                <title>{{ p.label }}：{{ p.requests }} 次 / {{ formatTokens(p.tokens) }} tokens</title>
              </rect>
            </g>
          </svg>
          <div class="x-axis">
            <span v-for="p in points" :key="'x' + p.label">{{ p.label }}</span>
          </div>
        </div>
        <div v-else class="empty-tip">近 7 天暂无请求</div>
      </BaseSection>

      <BaseSection variant="card" title="上游源贡献占比">
        <template #actions>
          <span class="axis-hint">按 Tokens · 近 7 天</span>
        </template>
        <div v-if="upstreamUsage.length" class="share-list">
          <div v-for="(u, i) in upstreamUsage" :key="u.upstream_id" class="share-item">
            <div class="share-head">
              <span class="share-name">
                <i class="share-dot" :style="{ background: pickColor(i) }"></i>
                {{ u.upstream_name || u.upstream_id }}
              </span>
              <span class="share-num">{{ formatTokens(u.total_tokens) }} · {{ (u.share * 100).toFixed(1) }}%</span>
            </div>
            <div class="share-track">
              <div class="share-fill" :style="{ width: Math.max(u.share * 100, 2) + '%', background: pickColor(i) }"></div>
            </div>
            <div class="share-meta">
              {{ u.requests }} 次请求
              <span v-if="u.error_count" class="err">· {{ u.error_count }} 失败</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-tip">近 7 天暂无上游用量</div>
      </BaseSection>
    </div>

    <!-- ④ 上游源卡片 -->
    <BaseSection variant="card" title="上游源">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="router.push('/upstreams')">管理上游源</BaseButton>
      </template>
      <div v-if="upstreamCards.length" class="up-grid">
        <div v-for="u in upstreamCards" :key="u.id" class="up-card" :class="{ 'is-disabled': !u.enabled }">
          <div class="up-head">
            <span class="up-dot" :class="u.enabled ? (u.probe_total && u.probe_ok === u.probe_total ? 'ok' : u.probe_ok ? 'part' : 'unknown') : 'off'"></span>
            <span class="up-name">{{ u.name || u.id }}</span>
            <BaseBadge v-for="g in u._groups" :key="g" :variant="g === 'free' ? 'blue' : 'amber'">{{ g }}</BaseBadge>
          </div>
          <div class="up-stats">
            <div class="up-stat">
              <span class="us-num">{{ u.modelCount }}</span>
              <span class="us-label">模型</span>
            </div>
            <div class="up-stat">
              <span class="us-num">{{ u.keyCount }}</span>
              <span class="us-label">Key</span>
            </div>
            <div class="up-stat">
              <span class="us-num">{{ u.requests7d }}</span>
              <span class="us-label">7天请求</span>
            </div>
            <div class="up-stat">
              <span class="us-num">{{ formatTokens(u.tokens7d) }}</span>
              <span class="us-label">Tokens</span>
            </div>
          </div>
          <div class="up-foot">
            <span class="up-probe">
              探测
              <template v-if="u.probe_total">
                <b :class="u.probe_ok === u.probe_total ? 'good' : 'warn'">{{ u.probe_ok }}/{{ u.probe_total }}</b>
              </template>
              <span v-else class="muted">未纳入</span>
            </span>
            <BaseBadge v-if="u.smart_retry" variant="purple">智能重试</BaseBadge>
            <BaseBadge v-if="!u.enabled" variant="gray">已禁用</BaseBadge>
          </div>
        </div>
      </div>
      <div v-else class="empty-tip">暂无上游源，请先到「上游源管理」添加</div>
    </BaseSection>

    <!-- ⑤ 聚合组概览 -->
    <BaseSection variant="card" title="聚合组" style="margin-top: 16px">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="router.push('/aggregated')">管理聚合</BaseButton>
      </template>
      <div v-if="groups.length" class="grp-grid">
        <div v-for="g in groups" :key="g.model" class="grp-card">
          <div class="grp-head">
            <code class="grp-model">{{ g.model }}</code>
            <BaseBadge :variant="g.configured ? 'blue' : 'gray'">{{ g.configured ? '手动配置' : '自动发现' }}</BaseBadge>
            <BaseBadge v-if="g.probe_enabled" variant="green">
              探测 {{ g.probe_interval }}s
            </BaseBadge>
            <BaseBadge v-else variant="gray">探测 关</BaseBadge>
            <BaseBadge v-if="g.probe_schedule_mode === 'window'" variant="amber">{{ g.probe_schedule }}</BaseBadge>
            <BaseBadge variant="default">{{ g.sort_mode === 'latency' ? '速度优先' : '稳定优先' }}</BaseBadge>
          </div>
          <div class="grp-flow">
            <template v-for="(m, i) in g.members" :key="m.upstream + m.model">
              <span class="grp-chip">
                <span class="chip-src">{{ m.upstream }}</span>
                <code>{{ m.model }}</code>
              </span>
              <span v-if="i < g.members.length - 1" class="grp-arrow">→</span>
            </template>
          </div>
          <div class="grp-foot">
            <span>近 7 天 <b>{{ g.requests_7d }}</b> 次 · <b>{{ formatTokens(g.tokens_7d) }}</b> tokens</span>
          </div>
        </div>
      </div>
      <div v-else class="empty-tip">暂无聚合组（同名模型分布在 2 个以上源时自动出现）</div>
    </BaseSection>

    <!-- ⑥ 需要关注 -->
    <BaseSection v-if="attention.length" variant="card" title="需要关注" style="margin-top: 16px">
      <div class="attn-list">
        <div v-for="(a, i) in attention" :key="i" class="attn-item" :class="'k-' + a.kind">
          <span class="attn-tag">{{ ATTENTION_LABEL[a.kind] || a.kind }}</span>
          <span class="attn-target">{{ a.target }}</span>
          <span class="attn-detail">{{ a.detail }}</span>
        </div>
      </div>
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { getDashboard } from '@/api/common'
import { listUpstreams } from '@/api/upstreams'
import { listApiKeys } from '@/api/apiKeys'

const router = useRouter()

const CHART_W = 720
const CHART_H = 180
const PAD_L = 8
const PAD_R = 8
const PAD_T = 12
const PAD_B = 8

const ATTENTION_LABEL: Record<string, string> = {
  cooldown: '冷却中',
  probe_down: '探测不可用',
  no_key: '无可用 Key',
  stale: '数据陈旧',
  disabled_upstream: '已禁用',
}

const dashboard = reactive<any>({
  usage_today: { requests: 0, success_rate: null, total_tokens: 0, active_keys: 0, requests_delta: null },
  usage_7d: { requests: 0, total_tokens: 0, success_rate: null },
  trend: [] as any[],
  probe_summary: {
    enabled: false, unit_count: 0, ok: 0, down: 0, unknown: 0,
    global_interval: 120, global_schedule: '全天候', scheduled_off: 0,
  },
  upstream_usage: [] as any[],
  groups: [] as any[],
  attention: [] as any[],
  api_key_count: 0,
})

const upstreams = ref<any[]>([])
const apiKeys = ref<any[]>([])

const usageToday = computed(() => dashboard.usage_today || {})
const usage7d = computed(() => dashboard.usage_7d || {})
const probeSummary = computed(() => dashboard.probe_summary || {})
const attention = computed(() => dashboard.attention || [])
const upstreamUsage = computed(() => dashboard.upstream_usage || [])
const groups = computed(() => dashboard.groups || [])

const rateColor = computed(() => {
  const r = usage7d.value.success_rate
  if (r === null || r === undefined) return 'var(--text-primary)'
  if (r >= 0.99) return 'var(--accent-green)'
  if (r >= 0.95) return 'var(--accent-yellow, #e6a23c)'
  return 'var(--accent-red)'
})

// ---------- 指标卡 ----------
const metrics = computed(() => {
  const totalMembers = groups.value.reduce((s: number, g: any) => s + (g.member_count || 0), 0)
  return [
    {
      label: '今日请求',
      value: usageToday.value.requests ?? 0,
      delta: usageToday.value.requests_delta,
      sub: `7 天累计 ${usage7d.value.requests ?? 0} 次`,
      to: '/usage',
    },
    {
      label: '今日 Tokens',
      value: formatTokens(usageToday.value.total_tokens || 0),
      delta: null,
      sub: `7 天 ${formatTokens(usage7d.value.total_tokens || 0)}`,
      to: '/usage',
    },
    {
      label: '今日成功率',
      value: formatRate(usageToday.value.success_rate),
      delta: null,
      sub: `7 天 ${formatRate(usage7d.value.success_rate)}`,
      to: '/usage',
    },
    {
      label: '活跃 Key',
      value: usageToday.value.active_keys ?? 0,
      delta: null,
      sub: `共 ${apiKeys.value.length} 把客户端 Key`,
      to: '/api-keys',
    },
    {
      label: '聚合组',
      value: groups.value.length,
      delta: null,
      sub: `${totalMembers} 个源成员 · 探测 ${groups.value.filter((g: any) => g.probe_enabled).length} 组开启`,
      to: '/aggregated',
    },
  ]
})

// ---------- 上游卡片 ----------
const upstreamCards = computed(() => {
  const usageMap = new Map<string, any>()
  for (const u of upstreamUsage.value) usageMap.set(u.upstream_id, u)
  return upstreams.value.map((u: any) => {
    const used = usageMap.get(u.id) || {}
    return {
      ...u,
      _groups: u.groups && u.groups.length ? u.groups : [u.group || 'free'],
      modelCount: (u.models || []).length,
      keyCount: (u.keys || []).length,
      requests7d: used.requests ?? 0,
      tokens7d: used.total_tokens ?? 0,
      probe_ok: used.probe_ok ?? 0,
      probe_total: used.probe_total ?? 0,
    }
  })
})

// ---------- 趋势图 ----------
const hasTrend = computed(() => {
  const t = dashboard.trend || []
  return t.some((p: any) => (p.requests || 0) > 0 || (p.total_tokens || 0) > 0)
})

const points = computed(() => {
  const trend = dashboard.trend || []
  if (!trend.length) return []
  const n = trend.length
  const maxReq = Math.max(...trend.map((p: any) => p.requests || 0), 1)
  const maxTok = Math.max(...trend.map((p: any) => p.total_tokens || 0), 1)
  const innerW = CHART_W - PAD_L - PAD_R
  const innerH = CHART_H - PAD_T - PAD_B
  return trend.map((p: any, i: number) => {
    const x = PAD_L + (n === 1 ? innerW / 2 : (innerW * i) / (n - 1))
    const ry = PAD_T + innerH - ((p.requests || 0) / maxReq) * innerH
    const ty = PAD_T + innerH - ((p.total_tokens || 0) / maxTok) * innerH
    return {
      x, ry, ty,
      label: p.date,
      requests: p.requests || 0,
      tokens: p.total_tokens || 0,
    }
  })
})

const reqLine = computed(() => points.value.map((p: any) => `${p.x},${p.ry}`).join(' '))
const tokLine = computed(() => points.value.map((p: any) => `${p.x},${p.ty}`).join(' '))
const reqArea = computed(() => {
  if (!points.value.length) return ''
  const base = CHART_H - PAD_B
  const first = points.value[0]
  const last = points.value[points.value.length - 1]
  return `${first.x},${base} ${reqLine.value} ${last.x},${base}`
})

function gridY(i: number): number {
  const innerH = CHART_H - PAD_T - PAD_B
  return PAD_T + (innerH * i) / 4
}

const COLORS = ['#4f8cff', '#8f6cff', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4']
function pickColor(i: number): string {
  return COLORS[i % COLORS.length]
}

function formatRate(r: number | null | undefined): string {
  if (r === null || r === undefined) return '—'
  return (r * 100).toFixed(1) + '%'
}

function formatTokens(n: number): string {
  if (!n) return '0'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

async function loadAll() {
  const [dash, ups, keys]: any[] = await Promise.all([
    getDashboard(),
    listUpstreams(),
    listApiKeys(),
  ])
  Object.assign(dashboard, dash)
  upstreams.value = ups.upstreams || []
  apiKeys.value = keys.api_keys || []
}

onMounted(loadAll)
</script>

<style scoped>
.dash {
  padding-bottom: 24px;
}

/* ---------- 健康条 ---------- */
.health-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-radius: 10px;
  background: var(--bg-base);
  border: 1px solid var(--border-subtle);
  margin-bottom: 16px;
}
.health-bar.is-warn {
  border-color: rgba(239, 68, 68, 0.28);
  background: linear-gradient(90deg, rgba(239, 68, 68, 0.05), transparent 40%);
}
.hb-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 13px;
}
.hb-label {
  color: var(--text-tertiary);
}
.hb-value {
  font-weight: 600;
}
.hb-sub {
  color: var(--text-tertiary);
  font-size: 12px;
}
.hb-sep {
  width: 1px;
  height: 14px;
  background: var(--border-subtle);
}
.hb-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
  align-self: center;
}
.hb-dot.on { background: var(--accent-green); box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.16); }
.hb-dot.off { background: var(--text-tertiary); }
.hb-actions {
  margin-left: auto;
}

/* ---------- 指标卡 ---------- */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.metric-card {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-base);
  cursor: pointer;
  transition: border-color 0.16s, transform 0.16s;
}
.metric-card:hover {
  border-color: var(--accent-blue, #4f8cff);
  transform: translateY(-1px);
}
.mc-label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}
.mc-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.mc-delta {
  font-size: 12px;
  font-weight: 600;
}
.mc-delta.up { color: var(--accent-green); }
.mc-delta.down { color: var(--accent-red); }
.mc-sub {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 6px;
}

/* ---------- 两栏 ---------- */
.two-col {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 16px;
}
.legend {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.lg-item { display: inline-flex; align-items: center; gap: 5px; }
.lg-dot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.axis-hint { font-size: 12px; color: var(--text-tertiary); }

.chart-wrap { padding-top: 4px; }
.trend-svg {
  display: block;
  overflow: visible;
}
.grid-line {
  stroke: var(--border-subtle);
  stroke-width: 1;
  stroke-dasharray: 3 4;
}
.x-axis {
  display: flex;
  justify-content: space-between;
  padding: 6px 8px 0;
  font-size: 11px;
  color: var(--text-tertiary);
}

/* ---------- 贡献占比 ---------- */
.share-list { display: flex; flex-direction: column; gap: 10px; }
.share-head {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  margin-bottom: 4px;
}
.share-name { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; }
.share-dot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.share-num { color: var(--text-tertiary); }
.share-track {
  height: 6px;
  border-radius: 4px;
  background: var(--bg-hover);
  overflow: hidden;
}
.share-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s;
}
.share-meta {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin-top: 3px;
}
.share-meta .err { color: var(--accent-red); }

/* ---------- 上游卡片 ---------- */
.up-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.up-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 12px 14px;
  background: var(--bg-base);
}
.up-card.is-disabled { opacity: 0.55; }
.up-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.up-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.up-dot.ok { background: var(--accent-green); }
.up-dot.part { background: var(--accent-yellow, #e6a23c); }
.up-dot.unknown { background: var(--text-tertiary); }
.up-dot.off { background: var(--border-subtle); }
.up-name {
  font-weight: 600;
  font-size: 13px;
  margin-right: auto;
}
.up-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  margin-bottom: 10px;
}
.up-stat { display: flex; flex-direction: column; }
.us-num { font-size: 14px; font-weight: 700; }
.us-label { font-size: 10.5px; color: var(--text-tertiary); }
.up-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
  padding-top: 8px;
  border-top: 1px dashed var(--border-subtle);
}
.up-probe b.good { color: var(--accent-green); }
.up-probe b.warn { color: var(--accent-yellow, #e6a23c); }
.muted { color: var(--text-tertiary); }

/* ---------- 聚合组 ---------- */
.grp-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.grp-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 12px 14px;
  background: var(--bg-base);
}
.grp-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.grp-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 13px;
  font-weight: 600;
}
.grp-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 8px;
}
.grp-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-hover);
  font-size: 11.5px;
}
.chip-src { color: var(--text-tertiary); }
.grp-chip code { font-family: var(--font-mono, ui-monospace, monospace); }
.grp-arrow { color: var(--text-tertiary); font-size: 11px; }
.grp-foot {
  font-size: 12px;
  color: var(--text-tertiary);
}
.grp-foot b { color: var(--text-primary); }

/* ---------- 待关注 ---------- */
.attn-list { display: flex; flex-direction: column; gap: 6px; }
.attn-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: 8px;
  background: var(--bg-hover);
  font-size: 12.5px;
}
.attn-tag {
  flex: 0 0 auto;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.k-cooldown .attn-tag, .k-probe_down .attn-tag { background: rgba(239, 68, 68, 0.12); color: var(--accent-red); }
.k-no_key .attn-tag, .k-stale .attn-tag { background: rgba(245, 158, 11, 0.14); color: #b45309; }
.k-disabled_upstream .attn-tag { background: var(--bg-base); color: var(--text-tertiary); }
.attn-target {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 600;
}
.attn-detail { color: var(--text-tertiary); }

.empty-tip {
  color: var(--text-tertiary);
  font-size: 13px;
  padding: 16px 0;
  text-align: center;
}

@media (max-width: 1280px) {
  .metric-grid { grid-template-columns: repeat(3, 1fr); }
  .up-grid { grid-template-columns: repeat(2, 1fr); }
  .two-col { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .up-grid { grid-template-columns: 1fr; }
  .grp-grid { grid-template-columns: 1fr; }
}
</style>
