<template>
  <div>
    <!-- 延迟探测 -->
    <BaseSection variant="card" title="延迟探测">
      <el-form :model="probeForm" label-width="120px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="启用延迟探测">
              <el-switch v-model="probeForm.enabled" />
            </el-form-item>
            <el-form-item label="探测间隔（秒）">
              <el-input-number v-model="probeForm.interval_seconds" :min="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="探测超时（秒）">
              <el-input-number v-model="probeForm.timeout_seconds" :min="5" style="width: 100%" />
            </el-form-item>
            <el-form-item label="探测 max_tokens">
              <el-input-number v-model="probeForm.max_tokens" :min="1" :max="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="不可用阈值（秒）">
              <el-input-number v-model="probeForm.down_threshold_seconds" :min="5" style="width: 100%" />
            </el-form-item>
            <el-form-item label="基准延迟（秒）">
              <el-input-number v-model="probeForm.base_latency" :min="0.1" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <BaseButton variant="primary" :disabled="saving" @click="handleSaveProbe">
            {{ saving ? '保存中...' : '保存探测设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 请求重试 -->
    <BaseSection variant="card" title="请求重试">
      <el-form :model="retryForm" label-width="140px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="最大重试次数">
              <el-input-number v-model="retryForm.max_attempts" :min="1" :max="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="响应超时（秒）">
              <el-input-number v-model="retryForm.response_timeout" :min="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="首包超时（秒）">
              <el-input-number v-model="retryForm.first_chunk_timeout" :min="5" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <BaseButton variant="primary" :disabled="saving" @click="handleSaveRetry">
            {{ saving ? '保存中...' : '保存重试设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 智能重试 -->
    <BaseSection variant="card" title="智能重试（全局参数）">
      <el-text type="info" size="small" style="margin-bottom: 12px; display: block">
        仅对开启了「智能重试」的上游源生效（上游源编辑弹窗中开启）。失败后优先换 Key 立即重试；只剩同一个 Key 时按退避间隔等待后重试。
      </el-text>
      <el-form :model="smartRetryForm" label-width="160px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="额外重试次数">
              <el-input-number v-model="smartRetryForm.extra_attempts" :min="0" :max="5" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="退避间隔（毫秒，逗号分隔）">
              <BaseInput v-model="smartRetryBackoffText" placeholder="500, 1500" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="抖动比例（0-0.5）">
              <el-input-number v-model="smartRetryForm.jitter" :min="0" :max="0.5" :step="0.05" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <BaseButton variant="primary" :disabled="saving" @click="handleSaveSmartRetry">
            {{ saving ? '保存中...' : '保存智能重试设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 故障转移 -->
    <BaseSection variant="card" title="故障转移">
      <el-form :model="failoverForm" label-width="140px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="最大连续失败次数">
              <el-input-number v-model="failoverForm.max_fails" :min="1" :max="20" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="冷却时间（秒）">
              <el-input-number v-model="failoverForm.cooldown_seconds" :min="10" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <BaseButton variant="primary" :disabled="saving" @click="handleSaveFailover">
            {{ saving ? '保存中...' : '保存故障转移设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 配置操作 -->
    <BaseSection variant="card" title="配置操作">
      <BaseButton variant="primary" :disabled="reloading" @click="handleReload">
        {{ reloading ? '热重载中...' : '热重载配置' }}
      </BaseButton>
    </BaseSection>

    <!-- 分组管理 -->
    <BaseSection variant="card" title="分组管理">
      <el-text type="info" size="small" style="margin-bottom: 12px; display: block">
        上游源和 API Key 按分组做权限隔离：API Key 只能访问其所属分组的上游源。被上游源或 API Key 引用的分组不可删除。
      </el-text>
      <el-table :data="groupsForm" size="small" style="margin-bottom: 12px">
        <el-table-column label="分组名" min-width="180">
          <template #default="{ row }">
            <BaseInput v-model="row.name" placeholder="如: free、premium" style="max-width: 240px" />
          </template>
        </el-table-column>
        <el-table-column label="描述" min-width="280">
          <template #default="{ row }">
            <BaseInput v-model="row.description" placeholder="分组说明（可选）" style="max-width: 360px" />
          </template>
        </el-table-column>
        <el-table-column label="" width="80" align="center">
          <template #default="{ $index }">
            <BaseButton variant="danger" size="sm" @click="removeGroup($index)">删除</BaseButton>
          </template>
        </el-table-column>
      </el-table>
      <div style="display: flex; gap: 8px; align-items: center">
        <BaseButton variant="ghost" size="sm" @click="addGroup">+ 添加分组</BaseButton>
        <BaseButton variant="primary" size="sm" :disabled="savingGroups" @click="handleSaveGroups">
          {{ savingGroups ? '保存中...' : '保存分组' }}
        </BaseButton>
      </div>
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import {
  getFailoverConfig,
  getProbeConfig,
  getRetryConfig,
  getSmartRetryConfig,
  saveFailoverConfig,
  saveProbeConfig,
  saveRetryConfig,
  saveSmartRetryConfig,
} from '@/api/settings'
import { reloadConfig } from '@/api/common'
import { listGroups, updateGroups } from '@/api/groups'
import BaseInput from '@/components/base/BaseInput.vue'

const saving = ref(false)
const reloading = ref(false)
const savingGroups = ref(false)

const probeForm = reactive<any>({})
const retryForm = reactive<any>({})
const failoverForm = reactive<any>({})
const smartRetryForm = reactive<any>({ extra_attempts: 2, backoff_ms: [500, 1500], jitter: 0.2 })
const smartRetryBackoffText = ref('500, 1500')
const groupsForm = ref<{ name: string; description: string }[]>([])

async function load() {
  const [probe, retry, failover, smartRetry, groups]: any = await Promise.all([
    getProbeConfig(),
    getRetryConfig(),
    getFailoverConfig(),
    getSmartRetryConfig(),
    listGroups(),
  ])
  Object.assign(probeForm, probe)
  Object.assign(retryForm, retry)
  Object.assign(failoverForm, failover)
  Object.assign(smartRetryForm, smartRetry)
  smartRetryBackoffText.value = (smartRetryForm.backoff_ms || []).join(', ')
  groupsForm.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
}

async function save(fn: any, form: any) {
  saving.value = true
  try {
    await fn({ ...form })
    ElMessage.success('设置已保存')
    await reloadConfig()
  } finally {
    saving.value = false
  }
}

const handleSaveProbe = () => save(saveProbeConfig, probeForm)
const handleSaveRetry = () => save(saveRetryConfig, retryForm)
const handleSaveFailover = () => save(saveFailoverConfig, failoverForm)

async function handleSaveSmartRetry() {
  const backoff = smartRetryBackoffText.value
    .split(/[,，\s]+/)
    .map((s) => parseInt(s, 10))
    .filter((n) => Number.isFinite(n) && n >= 0)
  if (!backoff.length) {
    ElMessage.warning('退避间隔格式不正确，示例：500, 1500')
    return
  }
  await save(saveSmartRetryConfig, { ...smartRetryForm, backoff_ms: backoff })
}

async function handleReload() {
  reloading.value = true
  try {
    await reloadConfig()
    ElMessage.success('配置已热重载')
  } finally {
    reloading.value = false
  }
}

function addGroup() {
  groupsForm.value.push({ name: '', description: '' })
}

function removeGroup(index: number) {
  groupsForm.value.splice(index, 1)
}

async function handleSaveGroups() {
  const groups = groupsForm.value.filter((g) => g.name.trim())
  if (!groups.length) {
    ElMessage.warning('至少保留一个分组')
    return
  }
  savingGroups.value = true
  try {
    await updateGroups(groups)
    ElMessage.success('分组已保存')
    await reloadConfig()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存分组失败')
  } finally {
    savingGroups.value = false
  }
}

onMounted(load)
</script>

