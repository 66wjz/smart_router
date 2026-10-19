<template>
  <div v-loading="loading">
    <BaseNotice v-if="loadFailed" variant="error" title="配置加载失败"
      text="请检查后端服务是否正常，然后点击下方按钮重试。" />
    <BaseButton v-if="loadFailed" variant="primary" style="margin-bottom: 16px" @click="load">重新加载</BaseButton>

    <!-- 全局容错 -->
    <BaseSection variant="card" title="全局容错">
      <BaseHint block style="margin-bottom: 12px"
        text="这些参数对所有请求生效，与具体聚合无关：请求重试决定一次请求最多尝试几个候选；智能重试只对开启了该开关的上游源生效；故障转移决定模型与 Key 的冷却策略。" />

      <el-divider content-position="left">请求重试</el-divider>
      <el-form :model="retryForm" label-width="160px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="最大尝试次数">
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
          <BaseButton variant="primary" size="sm" :disabled="saving" @click="handleSaveRetry">
            {{ saving ? '保存中...' : '保存重试设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>

      <el-divider content-position="left">智能重试</el-divider>
      <BaseHint block style="margin-bottom: 12px"
        text="仅对开启了「智能重试」的上游源生效（上游源编辑弹窗中开启）。失败后优先换 Key 立即重试；只剩同一个 Key 时按退避间隔等待后重试。" />
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
          <BaseButton variant="primary" size="sm" :disabled="saving" @click="handleSaveSmartRetry">
            {{ saving ? '保存中...' : '保存智能重试设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>

      <el-divider content-position="left">故障转移</el-divider>
      <el-form :model="failoverForm" label-width="160px">
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
          <BaseButton variant="primary" size="sm" :disabled="saving" @click="handleSaveFailover">
            {{ saving ? '保存中...' : '保存故障转移设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 同名模型聚合 -->
    <BaseSection variant="card" title="同名模型聚合" style="margin-top: 16px">
      <BaseHint block style="margin-bottom: 12px"
        text="多个上游源都存在同名模型时，是否自动把它当成一个聚合组。关闭后这类模型仍会跨源兜底（一个源失败自动换下一个），只是不再出现在聚合列表里、也不作为聚合参与权限判断。" />
      <el-form label-width="160px">
        <el-form-item label="自动聚合同名模型">
          <el-switch :model-value="autoAggregate" :loading="savingAutoAggregate"
            @update:model-value="(v: any) => handleSaveAutoAggregate(Boolean(v))" />
          <BaseHint inline
            :text="autoAggregate
              ? '已开启：同名模型分布在 ≥2 个源时会自动成为聚合组'
              : '已关闭（推荐）：同名模型只做跨源兜底，需聚合请在「聚合模型」页手动创建'" />
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 用量与日志（CH-038） -->
    <BaseSection variant="card" title="用量与日志" style="margin-top: 16px">
      <BaseHint block style="margin-bottom: 12px"
        text="请求详情会把原始请求、实际转发报文与上游响应一并存下来，便于排查。成功请求默认只记结构化字段与 token，失败请求才保存完整报文；保留期到期后主表与详情表会一起清理。" />
      <el-form label-width="160px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="详情采集模式">
              <el-select v-model="usageDetailForm.mode" style="width: 100%">
                <el-option label="关闭（不采集报文）" value="off" />
                <el-option label="仅失败请求（推荐）" value="error_only" />
                <el-option label="全部请求" value="all" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="单报文上限">
              <el-select v-model="usageDetailForm.max_bytes" style="width: 100%">
                <el-option label="64 KB" :value="65536" />
                <el-option label="256 KB" :value="262144" />
                <el-option label="1 MB（推荐）" :value="1048576" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="日志保留期">
              <el-select v-model="usageDetailForm.retention_days" style="width: 100%">
                <el-option label="7 天" :value="7" />
                <el-option label="14 天（默认）" :value="14" />
                <el-option label="30 天" :value="30" />
                <el-option label="90 天" :value="90" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <BaseHint block
          text="选择「全部请求」会显著增加数据库体积与写入开销；超过上限的报文按「头 3/4 + 尾 1/4」截断并标注。修改保留期后，下一轮清理（最长 1 小时）按新值生效。" />
        <el-form-item style="margin-top: 12px">
          <BaseButton variant="primary" size="sm" :disabled="savingUsageDetail" @click="handleSaveUsageDetail">
            {{ savingUsageDetail ? '保存中...' : '保存日志设置' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 分组管理 -->
    <BaseSection variant="card" title="分组管理" style="margin-top: 16px">
      <template #actions>
        <BaseButton variant="primary" size="sm" @click="addGroup">+ 添加分组</BaseButton>
      </template>
      <BaseHint block style="margin-bottom: 12px"
        text="上游源和 API Key 按分组做权限隔离：API Key 只能访问其所属分组的上游源。被上游源或 API Key 引用的分组不可删除。" />
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
        <BaseButton variant="primary" size="sm" :disabled="savingGroups" @click="handleSaveGroups">
          {{ savingGroups ? '保存中...' : '保存分组' }}
        </BaseButton>
      </div>
    </BaseSection>

    <!-- 配置操作 -->
    <BaseSection variant="card" title="配置操作" style="margin-top: 16px">
      <BaseHint block style="margin-bottom: 12px"
        text="延迟探测节奏与探测时段已移至「智能路由 → 聚合模型 → 探测计划」。若通过其他途径直接改了数据库，可点此手动重新加载全部配置（不影响正在处理的请求）。" />
      <BaseButton variant="primary" size="sm" :disabled="reloading" @click="handleReload">
        {{ reloading ? '热重载中...' : '热重载配置' }}
      </BaseButton>
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import { reloadConfig } from '@/api/common'
import { listGroups, updateGroups } from '@/api/groups'
import { getUsageDetailConfig, saveUsageDetailConfig } from '@/api/usage'
import {
  getAutoAggregateConfig,
  getFailoverConfig,
  getRetryConfig,
  getSmartRetryConfig,
  saveAutoAggregateConfig,
  saveFailoverConfig,
  saveRetryConfig,
  saveSmartRetryConfig,
} from '@/api/settings'

const loading = ref(false)
const loadFailed = ref(false)
const reloading = ref(false)
const saving = ref(false)
const savingGroups = ref(false)
const groupsForm = ref<{ name: string; description: string }[]>([])

/** CH-036：同名模型自动聚合开关 */
const autoAggregate = ref(false)
const savingAutoAggregate = ref(false)

/** CH-038：用量日志采集策略 */
const usageDetailForm = reactive({ mode: 'error_only', max_bytes: 1048576, retention_days: 14 })
const savingUsageDetail = ref(false)

const retryForm = reactive<any>({})
const failoverForm = reactive<any>({})
const smartRetryForm = reactive<any>({ extra_attempts: 2, backoff_ms: [500, 1500], jitter: 0.2 })
const smartRetryBackoffText = ref('500, 1500')

async function load() {
  loading.value = true
  loadFailed.value = false
  try {
    const [groups, retry, failover, smartRetry, autoAgg, usageDetail]: any = await Promise.all([
      listGroups(),
      getRetryConfig(),
      getFailoverConfig(),
      getSmartRetryConfig(),
      getAutoAggregateConfig().catch(() => ({ enabled: false })),
      getUsageDetailConfig().catch(() => ({ mode: 'error_only', max_bytes: 1048576, retention_days: 14 })),
    ])
    groupsForm.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
    autoAggregate.value = Boolean(autoAgg?.enabled)
    Object.assign(usageDetailForm, {
      mode: usageDetail?.mode || 'error_only',
      max_bytes: usageDetail?.max_bytes || 1048576,
      retention_days: usageDetail?.retention_days || 14,
    })
    Object.assign(retryForm, retry)
    Object.assign(failoverForm, failover)
    Object.assign(smartRetryForm, smartRetry)
    smartRetryBackoffText.value = (smartRetryForm.backoff_ms || []).join(', ')
  } catch {
    // 拦截器已弹出具体错误，这里只标记失败态，避免整页空白且无从下手
    loadFailed.value = true
  } finally {
    loading.value = false
  }
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

async function handleSaveAutoAggregate(enabled: boolean) {
  savingAutoAggregate.value = true
  try {
    await saveAutoAggregateConfig(enabled)
    autoAggregate.value = enabled
    ElMessage.success(enabled ? '已开启同名模型自动聚合' : '已关闭同名模型自动聚合')
    await reloadConfig()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingAutoAggregate.value = false
  }
}

async function handleSaveUsageDetail() {
  savingUsageDetail.value = true
  try {
    await saveUsageDetailConfig({ ...usageDetailForm })
    ElMessage.success('日志设置已保存')
    await reloadConfig()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingUsageDetail.value = false
  }
}

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

onMounted(load)
</script>
