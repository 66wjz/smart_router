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

    <!--
      分组管理（CH-048：改为展示型列表 + 弹窗编辑，对齐上游源）
      条目只读，点行内「修改」弹窗编辑，新增也走弹窗，每次操作即时提交。
    -->
    <ListPage
      title="分组管理"
      description="上游源和 API Key 按分组做权限隔离：API Key 只能访问其所属分组的上游源。被上游源或 API Key 引用的分组不可删除。"
      style="margin-top: 16px"
      :loading="loading"
      :page="groupPage"
      :page-size="groupPageSize"
      :total="groups.length"
      @update:page="groupPage = $event"
      @update:page-size="groupPageSize = $event"
    >
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="load">刷新</BaseButton>
        <BaseButton variant="primary" size="sm" @click="openGroupAdd">+ 添加分组</BaseButton>
      </template>

      <template #toolbar>
        <ListToolbar
          :count="selectedGroups.length"
          :total="groups.length"
          dataset="groups"
          :actions="groupBatchActions"
          selectable
          :all-checked="allGroupChecked"
          :indeterminate="groupIndeterminate"
          batch-export
          :selected-ids="selectedGroups"
          @toggle-all="toggleAllGroups"
          @clear="clearGroupSelection"
        />
      </template>

      <DataTable
        ref="groupTableRef"
        :data="pagedGroups"
        :columns="groupColumns"
        row-key="name"
        selectable
        empty-text="暂无分组，请点击右上角「添加分组」"
        @selection-change="(rows: any[]) => (selectedGroups = rows.map((r) => r.name))"
      >
        <template #cell-description="{ row }">
          {{ row.description || '—' }}
        </template>
        <template #cell-actions="{ row }">
          <RowActions
            :items="[
              { label: '修改', onClick: () => openGroupEdit(row) },
              { label: '删除', variant: 'danger', onClick: () => removeGroupRow(row) },
            ]"
          />
        </template>
      </DataTable>
    </ListPage>

    <!-- 新增 / 修改分组（CH-048：共用弹窗） -->
    <BaseModal v-model:visible="groupModal.visible" :title="groupModal.mode === 'add' ? '添加分组' : '修改分组'">
      <el-form :model="groupModal" label-width="90px">
        <el-form-item label="分组名" required>
          <BaseInput v-model="groupModal.name" placeholder="如: free、premium" />
          <BaseHint text="分组名是上游源与 API Key 的引用标识。改名后需自行把引用方改到新名字上；仍被引用的旧名无法删除。" />
        </el-form-item>
        <el-form-item label="描述">
          <BaseInput v-model="groupModal.description" placeholder="分组说明（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter
          :loading="groupModal.saving"
          :confirm-text="groupModal.mode === 'add' ? '确定添加' : '保存修改'"
          @cancel="groupModal.visible = false"
          @confirm="saveGroupModal"
        />
      </template>
    </BaseModal>

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
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import { ListPage, DataTable, ListToolbar, RowActions } from '@/components/list'
import type { DataColumn } from '@/components/list'
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
/** 分组列表（服务端真值，任何写入成功后都重拉） */
const groups = ref<{ name: string; description: string }[]>([])

// ---------- 分组管理：分页 + 多选 + 弹窗编辑（CH-048） ----------
const groupPage = ref(1)
const groupPageSize = ref(20)
const groupTableRef = ref<any>(null)
const selectedGroups = ref<string[]>([])

const pagedGroups = computed(() => {
  const start = (groupPage.value - 1) * groupPageSize.value
  return groups.value.slice(start, start + groupPageSize.value)
})

const groupColumns: DataColumn[] = [
  { key: 'name', label: '分组名', minWidth: 200 },
  { key: 'description', label: '描述', minWidth: 300 },
  { key: 'actions', label: '操作', width: 140, align: 'center' },
]

const groupPageNames = computed(() => pagedGroups.value.map((g) => g.name))
const allGroupChecked = computed(() =>
  groupPageNames.value.length > 0 && groupPageNames.value.every((n) => selectedGroups.value.includes(n)),
)
const groupIndeterminate = computed(() => {
  const hit = groupPageNames.value.filter((n) => selectedGroups.value.includes(n)).length
  return hit > 0 && hit < groupPageNames.value.length
})

function toggleAllGroups(checked: boolean) {
  if (checked) {
    selectedGroups.value = [...new Set([...selectedGroups.value, ...groupPageNames.value])]
  } else {
    const drop = new Set(groupPageNames.value)
    selectedGroups.value = selectedGroups.value.filter((n) => !drop.has(n))
  }
  groupTableRef.value?.setSelection?.(selectedGroups.value)
}

function clearGroupSelection() {
  selectedGroups.value = []
  groupTableRef.value?.clearSelection?.()
}

/**
 * 提交分组完整列表（CH-048：即时保存）。
 *
 * 后端 PUT /admin/api/groups 是全量替换语义，所以每次只改一处、
 * 其余原样带上。成功后重拉（后端会 strip 名字、丢空名），
 * 失败也重拉一次，把界面冲回服务端真值，避免「看着改了其实没改」。
 *
 * 错误提示交给 request.ts 的响应拦截器统一弹（它已经取了 detail），
 * 这里不再重复弹，否则同一条错误会弹两次。
 */
async function commitGroups(next: { name: string; description: string }[]): Promise<boolean> {
  try {
    await updateGroups(next)
    await load()
    return true
  } catch {
    await load()
    return false
  }
}

/** 新增 / 修改共用的弹窗状态（CH-048） */
const groupModal = reactive({
  visible: false,
  mode: 'add' as 'add' | 'edit',
  /** 编辑时记录原名，用于改名校验与生成新列表 */
  originalName: '',
  name: '',
  description: '',
  saving: false,
})

function openGroupAdd() {
  Object.assign(groupModal, { visible: true, mode: 'add', originalName: '', name: '', description: '', saving: false })
}

function openGroupEdit(row: { name: string; description: string }) {
  Object.assign(groupModal, {
    visible: true,
    mode: 'edit',
    originalName: row.name,
    name: row.name,
    description: row.description || '',
    saving: false,
  })
}

async function saveGroupModal() {
  const name = groupModal.name.trim()
  if (!name) {
    ElMessage.warning('分组名不能为空')
    return
  }
  // 重名校验：后端只去空不去重，前端先挡一道，避免出现两个同名分组
  const taken = groups.value.some(
    (g) => g.name === name && !(groupModal.mode === 'edit' && g.name === groupModal.originalName),
  )
  if (taken) {
    ElMessage.warning(`分组「${name}」已存在`)
    return
  }
  const description = groupModal.description.trim()
  const next =
    groupModal.mode === 'add'
      ? [...groups.value, { name, description }]
      : groups.value.map((g) =>
          g.name === groupModal.originalName ? { name, description } : g,
        )

  groupModal.saving = true
  const ok = await commitGroups(next)
  groupModal.saving = false
  if (ok) {
    groupModal.visible = false
    ElMessage.success(groupModal.mode === 'add' ? '分组已添加' : '分组已修改')
  }
}

async function removeGroupRow(row: { name: string; description: string }) {
  if (!(await confirmDanger(`确定删除分组「${row.name}」吗？`, '被上游源或 API Key 引用的分组无法删除。'))) return
  const ok = await commitGroups(groups.value.filter((g) => g.name !== row.name))
  if (ok) ElMessage.success('分组已删除')
}

/** 批量删除（CH-048）：一次提交，被引用的分组由后端统一拒绝 */
async function batchRemoveGroups() {
  const names = new Set(selectedGroups.value)
  if (!names.size) return
  if (!(await confirmDanger(`确定删除选中的 ${names.size} 个分组吗？`, '被上游源或 API Key 引用的分组无法删除。'))) return
  const ok = await commitGroups(groups.value.filter((g) => !names.has(g.name)))
  if (ok) {
    ElMessage.success('分组已删除')
    clearGroupSelection()
  }
}

const groupBatchActions = computed(() => [
  { label: '批量删除', variant: 'danger' as const, onClick: () => batchRemoveGroups() },
])

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
    const [groupResp, retry, failover, smartRetry, autoAgg, usageDetail]: any = await Promise.all([
      listGroups(),
      getRetryConfig(),
      getFailoverConfig(),
      getSmartRetryConfig(),
      getAutoAggregateConfig().catch(() => ({ enabled: false })),
      getUsageDetailConfig().catch(() => ({ mode: 'error_only', max_bytes: 1048576, retention_days: 14 })),
    ])
    groups.value = (groupResp.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
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
