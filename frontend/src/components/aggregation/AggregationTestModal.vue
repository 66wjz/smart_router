<template>
  <BaseModal :visible="visible" :title="`测试聚合：${name}`" size="wide"
    @update:visible="(v: boolean) => emit('update:visible', v)">
    <div class="ag-test-head">
      <BaseInput v-model="prompt" placeholder="测试提示词" :disabled="running"
        @keydown.enter="start" />
      <BaseButton variant="primary" size="sm" :disabled="running" @click="start">
        {{ running ? '测试中…' : '开始测试' }}
      </BaseButton>
    </div>
    <BaseHint :text="kind === 'rule'
      ? '规则聚合按绑定规则的候选并集逐个测试（最多 20 个），再按真实规则路由走一次。测试不写用量、不影响在线健康状态。'
      : '逐个成员独立测试；权重份额按当前启用成员计算。最后再按真实权重分发走一次聚合。测试不写用量、不影响在线健康状态。'" />

    <div v-if="error" class="ag-test-error">{{ error }}</div>

    <template v-if="result">
      <div class="ag-test-summary">
        <BaseBadge variant="green">通过 {{ result.summary.ok }}</BaseBadge>
        <BaseBadge variant="red">失败 {{ result.summary.fail }}</BaseBadge>
        <BaseBadge variant="gray">跳过 {{ result.summary.skipped }}</BaseBadge>
        <span v-if="result.truncated" class="ag-test-note">候选较多，只测前 20 个</span>
      </div>

      <div class="ag-test-section">成员逐个测试</div>
      <div class="ag-test-rows">
        <div v-for="(m, i) in result.members" :key="`${m.upstream}|${m.model}|${i}`" class="ag-test-row">
          <BaseBadge :variant="badgeOf(m.status)">{{ labelOf(m.status) }}</BaseBadge>
          <span class="ag-test-up">{{ m.upstream }}</span>
          <code class="ag-test-model">{{ m.model }}</code>
          <span v-if="m.weight" class="ag-test-weight">权重 ×{{ m.weight }} · {{ pct(m.share) }}</span>
          <span v-if="m.cooling" class="ag-test-cool">冷却中（不参与分发）</span>
          <span class="ag-test-latency">{{ m.latency_ms != null ? m.latency_ms + ' ms' : '' }}</span>
          <div class="ag-test-detail">{{ detailOf(m) }}</div>
        </div>
      </div>

      <template v-if="result.aggregate">
        <div class="ag-test-section">走聚合一次（真实权重分发）</div>
        <div class="ag-test-agg">
          <BaseBadge :variant="result.aggregate.ok ? 'green' : 'red'">
            {{ result.aggregate.ok ? '成功' : '失败' }}
          </BaseBadge>
          <template v-if="result.aggregate.served">
            <span class="ag-test-up">{{ result.aggregate.served.upstream }}</span>
            <code class="ag-test-model">{{ result.aggregate.served.model }}</code>
            <span class="ag-test-latency">{{ result.aggregate.served.latency_ms }} ms</span>
            <div class="ag-test-detail">{{ result.aggregate.served.content || '（无文本回复）' }}</div>
          </template>
          <template v-else>
            <span class="ag-test-detail">{{ result.aggregate.error }}（候选 {{ result.aggregate.candidate_count }} 个）</span>
          </template>
        </div>
        <div v-if="result.aggregate.tried.length > 1" class="ag-test-tried">
          <div v-for="(t, i) in result.aggregate.tried" :key="`${t.upstream}|${t.model}|${i}`" class="ag-test-try">
            <BaseBadge :variant="t.ok ? 'green' : 'red'">{{ i + 1 }}</BaseBadge>
            <span class="ag-test-up">{{ t.upstream }}</span>
            <code class="ag-test-model">{{ t.model }}</code>
            <span class="ag-test-latency">{{ t.latency_ms }} ms</span>
            <span v-if="t.error" class="ag-test-detail">{{ t.error }}</span>
          </div>
        </div>
      </template>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import { testAggregation } from '@/api/aggregations'
import type { AggregationTestMember, AggregationTestResult } from '@/api/aggregations'

const props = defineProps<{
  visible: boolean
  name: string
  kind: 'static' | 'rule'
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const prompt = ref('你好，请回复一句话')
const running = ref(false)
const error = ref('')
const result = ref<AggregationTestResult | null>(null)

type BadgeVariant = 'default' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'gray'

function badgeOf(status: AggregationTestMember['status']): BadgeVariant {
  if (status === 'ok') return 'green'
  if (status === 'fail') return 'red'
  return 'gray'
}

function labelOf(status: AggregationTestMember['status']): string {
  if (status === 'ok') return '通过'
  if (status === 'fail') return '失败'
  return '跳过'
}

function pct(share: number | null): string {
  if (share == null) return ''
  return `${Math.round(share * 1000) / 10}%`
}

function detailOf(m: AggregationTestMember): string {
  if (m.status === 'ok') return m.content || '（无文本回复）'
  return m.error || ''
}

async function start() {
  if (running.value) return
  running.value = true
  error.value = ''
  try {
    result.value = (await testAggregation(props.name, { prompt: prompt.value })) as unknown as AggregationTestResult
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.response?.data?.error || e?.message || '测试失败'
  } finally {
    running.value = false
  }
}

watch(() => props.visible, (v) => {
  if (v) {
    error.value = ''
    result.value = null
  }
})
</script>

<style scoped>
.ag-test-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.ag-test-head :deep(.base-input) {
  flex: 1;
}
.ag-test-error {
  margin-top: 10px;
  color: var(--accent-red);
  font-size: 0.85rem;
}
.ag-test-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.ag-test-note {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}
.ag-test-section {
  margin: 14px 0 6px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
}
.ag-test-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ag-test-row,
.ag-test-agg,
.ag-test-try {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-md, 8px);
  background: var(--bg-hover);
  font-size: 0.82rem;
}
.ag-test-tried {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}
.ag-test-row {
  align-items: flex-start;
}
.ag-test-up {
  color: var(--text-secondary);
}
.ag-test-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
}
.ag-test-weight {
  color: var(--accent-amber);
  font-size: 0.78rem;
}
.ag-test-cool {
  color: var(--accent-red);
  font-size: 0.78rem;
}
.ag-test-latency {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}
.ag-test-detail {
  flex: 1 1 100%;
  color: var(--text-secondary);
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-word;
}
.ag-test-agg .ag-test-detail {
  flex: 1 1 auto;
}
</style>
