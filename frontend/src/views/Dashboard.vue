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
      <BaseSection variant="card" title="近 7 天用量趋势" class="trend-card">
        <template #actions>
          <div class="legend">
            <span class="lg-item"><i class="lg-dot dot-req"></i>请求数</span>
            <span class="lg-item"><i class="lg-dot dot-tok"></i>Tokens</span>
          </div>
        </template>
        <!-- CH-044：右栏变高时左栏卡片跟着撑满，图表吃掉剩余空间（不留灰底空白） -->
        <div v-if="hasTrend" class="chart-wrap">
          <svg :viewBox="`0 0 ${CHART_W} ${CHART_H}`" preserveAspectRatio="none"
               :width="CHART_W" :height="CHART_H"
               class="trend-svg">
            <defs>
              <linearGradient id="gReq" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" class="grad-req-start" />
                <stop offset="100%" class="grad-req-end" />
              </linearGradient>
            </defs>
            <!-- 网格线 -->
            <line v-for="g in 4" :key="'g' + g" :x1="PAD_L" :x2="CHART_W - PAD_R"
                  :y1="gridY(g)" :y2="gridY(g)" class="grid-line" />
            <!-- 请求数面积 + 折线 -->
            <polygon :points="reqArea" fill="url(#gReq)" />
            <polyline :points="reqLine" fill="none" stroke-width="2" stroke-linejoin="round" class="line-req" />
            <!-- Tokens 折线（虚线） -->
            <polyline :points="tokLine" fill="none" stroke-width="2"
                      stroke-dasharray="4 3" stroke-linejoin="round" opacity="0.85" class="line-tok" />
            <!-- 数据点 + 原生 tooltip -->
            <g v-for="(p, i) in points" :key="'p' + i">
              <circle :cx="p.x" :cy="p.ry" r="3.2" class="dot-req-fill" />
              <circle :cx="p.x" :cy="p.ty" r="2.6" class="dot-tok-fill" />
              <rect :x="p.x - 22" :y="0" width="44" height="26" fill="transparent">
                <title>{{ p.label }}：{{ p.requests }} 次 / {{ formatTokens(p.tokens) }} tokens</title>
              </rect>
            </g>
          </svg>
          <div class="x-axis">
            <span v-for="p in points" :key="'x' + p.label">{{ p.label }}</span>
          </div>
        </div>
        <BaseEmptyState v-else compact description="近 7 天暂无请求" />
      </BaseSection>

      <BaseSection variant="card" title="上游源贡献占比">
        <template #actions>
          <span class="axis-hint">按 Tokens · 近 7 天</span>
        </template>
        <!-- CH-043：上游多时内部滚动，避免把左栏图表撑高 -->
        <div v-if="upstreamUsage.length" class="share-list">
          <div v-for="(u, i) in upstreamUsage" :key="u.upstream_id" class="share-item">
            <div class="share-head">
              <span class="share-name" :title="u.upstream_name || u.upstream_id">
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
        <BaseEmptyState v-else compact description="近 7 天暂无上游用量" />
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
      <BaseEmptyState v-else description="暂无上游源，请先到「上游源管理」添加" />
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
          <ChipFlow
            v-if="g.members && g.members.length"
            :items="g.members"
            :page-size="10"
            arrow
          />
          <span v-else class="muted">无成员</span>
          <div class="grp-foot">
            <span>近 7 天 <b>{{ g.requests_7d }}</b> 次 · <b>{{ formatTokens(g.tokens_7d) }}</b> tokens</span>
          </div>
        </div>
      </div>
      <BaseEmptyState v-else description="暂无聚合组（同名模型分布在 2 个以上源时自动出现）" />
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
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import ChipFlow from '@/components/base/ChipFlow.vue'
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
  if (r >= 0.95) return 'var(--accent-amber)'
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

/** 图表分类色：CSS 变量优先，取不到时回退到同色硬编码（导出/截图场景） */
const COLORS = [
  'var(--chart-line-1, #4f8cff)',
  'var(--chart-line-2, #8f6cff)',
  'var(--chart-cat-green, #22c55e)',
  'var(--chart-cat-amber, #f59e0b)',
  'var(--chart-cat-red, #ef4444)',
  'var(--chart-cat-cyan, #06b6d4)',
]
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

<style scoped src="@/styles/dashboard.css"></style>
