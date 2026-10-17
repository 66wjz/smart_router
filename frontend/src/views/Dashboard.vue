<template>
  <div>
    <!-- 指标卡片：仅中转视角（路由视角已归入「智能路由」菜单） -->
    <div class="metric-grid">
      <BaseCard v-for="m in metrics" :key="m.label" variant="hoverable">
        <div class="metric-label">
          <span class="func-tag tag-relay">中转</span>{{ m.label }}
        </div>
        <div class="metric-value">{{ m.value }}</div>
        <div v-if="m.sub" class="metric-sub">{{ m.sub }}</div>
      </BaseCard>
    </div>

    <!-- 上游源状态一览 + 快速操作（同行等高） -->
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

      <BaseSection title="快速操作" variant="card" class="fill-card">
        <div class="quick-actions">
          <BaseButton variant="primary" block @click="router.push('/upstreams')">
            <BaseIcon name="server" :size="14" />
            管理上游源
          </BaseButton>
          <BaseButton variant="ghost" block @click="loadAll">
            <BaseIcon name="activity" :size="14" />
            刷新数据
          </BaseButton>
          <BaseButton variant="ghost" block @click="router.push('/route-params')">
            <BaseIcon name="zap" :size="14" />
            路由参数
          </BaseButton>
          <BaseButton variant="ghost" block @click="router.push('/usage')">
            <BaseIcon name="bar-chart" :size="14" />
            用量统计
          </BaseButton>
        </div>
      </BaseSection>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { getDashboard } from '@/api/common'
import { listUpstreams } from '@/api/upstreams'
import { listApiKeys } from '@/api/apiKeys'

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

const enabledUpstreamCount = computed(() => upstreams.value.filter((u) => u.enabled).length)
const totalModelCount = computed(() => upstreams.value.reduce((s, u) => s + (u.models || []).length, 0))
const totalKeyCount = computed(() => upstreams.value.reduce((s, u) => s + (u.keys || []).length, 0))
const keyGroupCoverage = computed(() => {
  const gs = new Set<string>()
  for (const k of apiKeys.value) for (const g of k.groups || []) gs.add(g)
  return [...gs].join(' / ') || '—'
})

const metrics = computed(() => [
  {
    label: '上游源',
    value: `${enabledUpstreamCount.value} 启用`,
    sub: `共 ${upstreams.value.length} 个 · 已配置模型 ${totalModelCount.value} 个 · ${totalKeyCount.value} 把上游 Key`,
  },
  {
    label: 'API Key',
    value: String(dashboard.api_key_count),
    sub: `覆盖分组：${keyGroupCoverage.value}`,
  },
])

async function loadAll() {
  const [dash, ups, keys]: any[] = await Promise.all([
    getDashboard(),
    listUpstreams(),
    listApiKeys(),
  ])
  Object.assign(dashboard, dash)
  upstreams.value = (ups.upstreams || []).map((u: any) => ({
    ...u,
    _groups: u.groups && u.groups.length ? u.groups : [u.group || 'free'],
  }))
  apiKeys.value = keys.api_keys || []
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
