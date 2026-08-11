<template>
  <div>
    <!-- 汇总卡片 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="8">
        <BaseCard variant="hoverable">
          <div class="metric-label">总模型</div>
          <div class="metric-value">{{ summary.total }}</div>
        </BaseCard>
      </el-col>
      <el-col :span="8">
        <BaseCard variant="hoverable">
          <div class="metric-label">可用</div>
          <div class="metric-value" style="color: var(--accent-green)">{{ summary.ok }}</div>
        </BaseCard>
      </el-col>
      <el-col :span="8">
        <BaseCard variant="hoverable">
          <div class="metric-label">不可用</div>
          <div class="metric-value" style="color: var(--accent-red)">{{ summary.down }}</div>
        </BaseCard>
      </el-col>
    </el-row>

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
        <h4 style="margin: 0 0 8px">规则: {{ rule.name }}</h4>
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
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { getStatus } from '@/api/common'

const loading = ref(false)
const latencyPanel = ref<Record<string, any>>({})
const rulesStatus = ref<any[]>([])

const latencyRows = computed(() =>
  Object.entries(latencyPanel.value).map(([model, info]: [string, any]) => ({
    model,
    latency: info.latency,
    status: info.status,
    error: info.error,
  }))
)

const summary = computed(() => {
  let ok = 0,
    down = 0
  Object.values(latencyPanel.value).forEach((info: any) => {
    if (info.status === 'ok') ok++
    else if (info.status === 'down') down++
  })
  return { total: Object.keys(latencyPanel.value).length, ok, down }
})

async function load() {
  loading.value = true
  try {
    const res: any = await getStatus()
    latencyPanel.value = res.latency_panel || {}
    rulesStatus.value = res.rules || []
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
</style>
