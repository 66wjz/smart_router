<template>
  <div>
    <!-- 指标卡片 -->
    <div class="metric-grid">
      <BaseCard v-for="m in metrics" :key="m.label" variant="hoverable">
        <div class="metric-label">{{ m.label }}</div>
        <div class="metric-value" :style="{ color: m.color }">{{ m.value }}</div>
        <div v-if="m.sub" class="metric-sub">{{ m.sub }}</div>
      </BaseCard>
    </div>

    <!-- 故障状态 + 快速操作 -->
    <div class="dashboard-row">
      <BaseSection title="模型故障状态" variant="card" class="fault-section">
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

      <BaseSection title="快速操作" variant="card" class="quick-section">
        <div class="quick-actions">
          <BaseButton variant="primary" block :disabled="reloading" @click="handleReload">
            <BaseIcon name="refresh-cw" :size="14" />
            热重载配置
          </BaseButton>
          <BaseButton variant="ghost" block @click="loadDashboard">
            <BaseIcon name="activity" :size="14" />
            刷新延迟数据
          </BaseButton>
        </div>
      </BaseSection>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { getDashboard, reloadConfig } from '@/api/common'

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

const metrics = computed(() => [
  { label: '上游源数', value: dashboard.upstream_count, color: 'var(--text-primary)' },
  { label: '候选模型数', value: dashboard.model_count, color: 'var(--text-primary)' },
  { label: '模型可用率', value: rate.value, sub: `${dashboard.model_ok} 可用 / ${dashboard.model_down} 不可用`, color: rateColor.value },
  { label: 'API Key 数', value: dashboard.api_key_count, color: 'var(--text-primary)' },
])

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

async function loadDashboard() {
  const res: any = await getDashboard()
  Object.assign(dashboard, res)
}

async function handleReload() {
  reloading.value = true
  try {
    await reloadConfig()
    ElMessage.success('配置已热重载')
    loadDashboard()
  } finally {
    reloading.value = false
  }
}

onMounted(loadDashboard)
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
}

.metric-value {
  font-size: 28px;
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
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  align-items: start;
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
