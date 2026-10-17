<template>
  <div>
    <el-alert
      title="这里是与智能路由相关的运行参数：延迟探测、请求重试、智能重试与故障转移。修改后点保存即热重载生效。"
      type="info"
      :closable="false"
      style="margin-bottom: 16px"
    />

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

    <!-- 配置生效 -->
    <BaseSection variant="card" title="配置生效">
      <el-text type="info" size="small" style="margin-bottom: 12px; display: block">
        各区块保存后会自动热重载。若通过其他途径直接改了数据库，可点此手动重新加载全部配置（不影响正在处理的请求）。
      </el-text>
      <BaseButton variant="ghost" :disabled="reloading" @click="handleReload">
        <BaseIcon name="refresh-cw" :size="14" />
        {{ reloading ? '热重载中...' : '重新加载配置' }}
      </BaseButton>
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import BaseInput from '@/components/base/BaseInput.vue'
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

const saving = ref(false)
const reloading = ref(false)
const probeForm = reactive<any>({})
const retryForm = reactive<any>({})
const failoverForm = reactive<any>({})
const smartRetryForm = reactive<any>({ extra_attempts: 2, backoff_ms: [500, 1500], jitter: 0.2 })
const smartRetryBackoffText = ref('500, 1500')

async function load() {
  const [probe, retry, failover, smartRetry]: any = await Promise.all([
    getProbeConfig(),
    getRetryConfig(),
    getFailoverConfig(),
    getSmartRetryConfig(),
  ])
  Object.assign(probeForm, probe)
  Object.assign(retryForm, retry)
  Object.assign(failoverForm, failover)
  Object.assign(smartRetryForm, smartRetry)
  smartRetryBackoffText.value = (smartRetryForm.backoff_ms || []).join(', ')
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
    ElMessage.success('配置已重新加载')
  } finally {
    reloading.value = false
  }
}

onMounted(load)
</script>
