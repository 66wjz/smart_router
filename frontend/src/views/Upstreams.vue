<template>
  <BaseSection variant="card" title="上游源列表">
    <div class="toolbar">
      <BaseButton variant="primary" size="sm" @click="openAdd">+ 添加上游源</BaseButton>
    </div>

    <!-- 上游源卡片列表 -->
    <div v-loading="loading">
      <el-empty v-if="!upstreams.length && !loading" description="暂无上游源，请点击上方按钮添加" />
      <div v-for="u in upstreams" :key="u.id" class="upstream-card" :class="{ 'is-disabled': !u.enabled }">
        <div class="upstream-header">
          <div class="upstream-title">
            <span class="upstream-name">{{ u.name }}</span>
            <BaseBadge variant="gray">{{ u.format }}</BaseBadge>
            <BaseBadge v-if="u.smart_retry" variant="blue">智能重试</BaseBadge>
            <BaseBadge v-for="g in (u.groups && u.groups.length ? u.groups : [u.group])" :key="g" variant="green">{{ g }}</BaseBadge>
            <BaseBadge :variant="u.enabled ? 'green' : 'gray'">{{ u.enabled ? '已启用' : '已禁用' }}</BaseBadge>
          </div>
          <div class="upstream-actions">
            <el-switch
              :model-value="u.enabled"
              :loading="togglingIds.includes(u.id)"
              active-text="启用"
              inactive-text="禁用"
              @change="(val: boolean | string | number) => handleToggle(u, Boolean(val))"
            />
            <BaseButton variant="ghost" size="sm" @click="openEdit(u)">修改</BaseButton>
            <BaseButton variant="danger" size="sm" @click="handleDelete(u)">删除</BaseButton>
          </div>
        </div>
        <div class="upstream-meta">
          ID: <el-text type="info" size="small">{{ u.id }}</el-text> &nbsp;·&nbsp;
          Base URL: <el-text type="info" size="small">{{ u.base_url }}</el-text> &nbsp;·&nbsp;
          <el-text type="info" size="small">{{ u.key_count }} 个 Key</el-text>
          <template v-if="u.key_count > 1">
            &nbsp;·&nbsp; 首 Key: <el-text type="info" size="small">{{ u.api_key }}</el-text>
          </template>
        </div>

        <!-- 已配置模型列表（持久化） -->
        <div class="model-section">
          <div class="model-head">
            <div class="model-title">
              已配置模型
              <span class="model-count">（{{ modelsByUpstream[u.id]?.length || 0 }} 个）</span>
            </div>
            <div class="model-ops">
              <BaseButton
                variant="primary"
                size="sm"
                :disabled="testingAll[u.id] || !(modelsByUpstream[u.id] || []).length"
                @click="testAllModels(u)"
              >
                {{ testingAll[u.id] ? `测试中 ${testProgress[u.id] || ''}` : '全量测试' }}
              </BaseButton>
              <BaseButton variant="ghost" size="sm" @click="openFetchPanel(u)">
                {{ fetchPanelOpen[u.id] ? '收起面板' : '拉取模型' }}
              </BaseButton>
              <BaseButton variant="ghost" size="sm" @click="openManualModal(u)">手动添加</BaseButton>
            </div>
          </div>

          <div v-if="modelsByUpstream[u.id] && modelsByUpstream[u.id].length" class="model-list" :data-sortable-upstream="u.id">
            <div class="model-batch-bar">
              <el-checkbox :model-value="allSelected(u)" @change="toggleSelectAllModels(u)">全选</el-checkbox>
              <span class="batch-count">已选 {{ selectedModelCount(u) }} 个</span>
              <div class="batch-ops">
                <BaseButton variant="danger" size="sm" :disabled="!selectedModelCount(u) || testingAll[u.id]" @click="batchDelete(u)">
                  批量删除
                </BaseButton>
                <BaseButton variant="primary" size="sm" :disabled="!selectedModelCount(u) || testingAll[u.id]" @click="batchTest(u)">
                  批量测试
                </BaseButton>
              </div>
            </div>
            <div
              v-for="m in visibleModels(u)"
              :key="m.name"
              class="model-row"
              :class="{ 'model-disabled': m.enabled === false }"
              :data-model="m.name"
            >
              <span
                class="drag-handle"
                role="button"
                tabindex="0"
                aria-label="拖动调整模型顺序"
                :class="{ 'is-disabled': modelExpanded[u.id] === false && (modelsByUpstream[u.id] || []).length > COLLAPSE_THRESHOLD }"
                :title="(modelsByUpstream[u.id] || []).length > COLLAPSE_THRESHOLD && !modelExpanded[u.id] ? '展开全部后可拖拽排序' : '拖动调整顺序'"
              >⠿</span>
              <el-checkbox v-model="modelSelected[u.id][m.name]" :disabled="testingAll[u.id]" />
              <code class="model-name">{{ m.name }}</code>
              <el-tag v-if="m.enabled === false" type="info" size="small">已禁用</el-tag>
              <el-select
                :model-value="m.protocol || 'inherit'"
                size="small"
                style="width: 160px"
                :disabled="testingAll[u.id]"
                @change="(val: string) => setModelProtocol(u, m.name, val)"
              >
                <el-option :label="`继承（${u.format}）`" value="inherit" />
                <el-option label="openai" value="openai" />
                <el-option label="anthropic" value="anthropic" />
                <el-option label="responses" value="responses" />
              </el-select>
              <span class="model-status">
                <BaseBadge :variant="modelStateBadge(u, m.name)">{{ modelStateText(u, m.name) }}</BaseBadge>
                <span v-if="modelStateDetail(u, m.name)" class="model-detail" :class="{ 'detail-fail': modelState(u, m.name)?.status === 'fail' }">{{ modelStateDetail(u, m.name) }}</span>
              </span>
              <BaseButton
                variant="primary"
                size="sm"
                :disabled="isTesting(u, m.name) || testingAll[u.id]"
                @click="testModel(u, m.name)"
              >
                {{ isTesting(u, m.name) ? '测试中...' : (modelState(u, m.name)?.status === 'ok' ? '再测' : '测试') }}
              </BaseButton>
              <BaseButton variant="danger" size="sm" :disabled="testingAll[u.id]" @click="removeModel(u, m.name)">删除</BaseButton>
              <div class="model-row-right">
                <el-switch
                  :model-value="m.enabled !== false"
                  size="small"
                  :disabled="testingAll[u.id] || togglingModels[`${u.id}:${m.name}`]"
                  @change="(val: boolean | string | number) => handleToggleModel(u, m.name, Boolean(val))"
                />
              </div>
            </div>
            <div v-if="(modelsByUpstream[u.id] || []).length > COLLAPSE_THRESHOLD" class="model-expand-bar">
              <BaseButton variant="ghost" size="sm" @click="toggleExpand(u)">
                {{ modelExpanded[u.id] ? '收起模型列表' : `展开全部（${modelsByUpstream[u.id].length} 个）` }}
              </BaseButton>
            </div>
          </div>
          <div v-else class="model-empty">
            <el-text type="info" size="small">暂无已配置模型，可点击「拉取模型」批量加入或「手动添加」</el-text>
          </div>

          <!-- 拉取结果面板 -->
          <div v-if="fetchPanelOpen[u.id]" class="fetch-panel">
            <div class="fetch-bar">
              <span class="fetch-title">拉取结果（共 {{ remoteModelsByUpstream[u.id]?.length || 0 }} 个）</span>
              <BaseInput v-model="fetchSearch[u.id]" size="sm" placeholder="搜索模型名…" style="width: 220px" />
              <BaseButton variant="ghost" size="sm" @click="toggleSelectAll(u)">全选</BaseButton>
            </div>
            <div class="fetch-chips">
              <BaseCheckTag
                v-for="m in filteredRemoteModels(u)"
                :key="m"
                v-model="remoteChecked[u.id][m]"
                size="sm"
              >
                {{ m }}
              </BaseCheckTag>
            </div>
            <div class="fetch-foot">
              <span class="fetch-count">已选 {{ selectedRemoteCount(u) }} 个</span>
              <BaseButton variant="primary" size="sm" :disabled="selectedRemoteCount(u) === 0" @click="handleJoin(u)">
                加入模型列表
              </BaseButton>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增上游源弹窗 -->
    <BaseModal v-model:visible="addVisible" title="添加上游源" size="wide">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="ID（唯一）" required>
          <BaseInput v-model="addForm.id" placeholder="例: newapi、xiaomi" />
        </el-form-item>
        <el-form-item label="显示名称" required>
          <BaseInput v-model="addForm.name" placeholder="例: NewAPI 中转站" />
        </el-form-item>
        <el-form-item label="Base URL" required>
          <BaseInput v-model="addForm.base_url" placeholder="http://..." />
          <div v-if="addForm.base_url.trim()" class="url-preview">
            <div>实际请求地址：<code>{{ buildEndpointPreview(addForm.base_url, addForm.format === 'anthropic' ? '/v1/messages' : '/v1/chat/completions') }}</code></div>
            <div>模型列表地址：<code>{{ buildEndpointPreview(addForm.base_url, '/v1/models') }}</code></div>
          </div>
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input
            v-model="addForm.api_keys_text"
            type="textarea"
            :rows="3"
            placeholder="每行一个 API Key，支持批量粘贴&#10;多个 Key 自动轮询分摊流量"
          />
          <el-text type="info" size="small">可填写多个 Key（每行一个），请求自动轮询；单个 Key 失败/限流自动换下一个</el-text>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="默认协议">
              <el-select v-model="addForm.format" style="width: 100%">
                <el-option label="openai" value="openai" />
                <el-option label="anthropic" value="anthropic" />
              </el-select>
              <el-text type="info" size="small">该源模型默认使用的协议；单个模型可在模型列表中单独覆盖</el-text>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="分组">
              <el-select v-model="addForm.groups" multiple placeholder="可多选，任意一个分组的 Key 都可访问本源" style="width: 100%">
                <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="延迟探测">
          <el-switch v-model="addForm.probe_enabled" />
        </el-form-item>
        <el-form-item label="智能重试">
          <el-switch v-model="addForm.smart_retry" />
          <el-text type="info" size="small" style="margin-left: 8px">开启后，5xx/超时/连接中断自动换 Key 或退避重试，客户端无感知。适合 opencode 等不稳定上游</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="addVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="adding" @click="handleAdd">
          {{ adding ? '添加中...' : '确定添加' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 修改上游源弹窗 -->
    <BaseModal v-model:visible="editVisible" title="修改上游源" size="wide">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="ID（不可改）">
          <el-input :model-value="editForm.id" disabled />
        </el-form-item>
        <el-form-item label="显示名称" required>
          <BaseInput v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="Base URL" required>
          <BaseInput v-model="editForm.base_url" />
          <div v-if="editForm.base_url.trim()" class="url-preview">
            <div>实际请求地址：<code>{{ buildEndpointPreview(editForm.base_url, editForm.format === 'anthropic' ? '/v1/messages' : '/v1/chat/completions') }}</code></div>
            <div>模型列表地址：<code>{{ buildEndpointPreview(editForm.base_url, '/v1/models') }}</code></div>
          </div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="editForm.keys_text"
            type="textarea"
            :rows="3"
            placeholder="每行一个 API Key&#10;留空表示不修改 Key 池"
          />
          <el-text type="info" size="small">回显现有 Key（每行一个）；清空则保持原 Key 池不变；非空则整体替换</el-text>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="默认协议">
              <el-select v-model="editForm.format" style="width: 100%">
                <el-option label="openai" value="openai" />
                <el-option label="anthropic" value="anthropic" />
              </el-select>
              <el-text type="info" size="small">该源模型默认使用的协议；单个模型可在模型列表中单独覆盖</el-text>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="分组">
              <el-select v-model="editForm.groups" multiple placeholder="可多选，任意一个分组的 Key 都可访问本源" style="width: 100%">
                <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="延迟探测">
          <el-switch v-model="editForm.probe_enabled" />
        </el-form-item>
        <el-form-item label="智能重试">
          <el-switch v-model="editForm.smart_retry" />
          <el-text type="info" size="small" style="margin-left: 8px">开启后，5xx/超时/连接中断自动换 Key 或退避重试，客户端无感知。适合 opencode 等不稳定上游</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="editVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="editing" @click="handleEditSave">
          {{ editing ? '保存中...' : '保存修改' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 手动添加模型弹窗 -->
    <BaseModal v-model:visible="manualModal.visible" title="手动添加模型" size="wide">
      <el-form :model="manualModal" label-width="90px">
        <el-form-item label="模型名" required>
          <BaseInput v-model="manualModal.input" placeholder="多个模型名用逗号分隔，如: gpt-4o, claude-3-5-sonnet" />
          <el-text type="info" size="small">已存在的模型名会自动跳过，不会重复添加</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="manualModal.visible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="manualModal.saving" @click="confirmManualAdd">
          {{ manualModal.saving ? '添加中...' : '添加' }}
        </BaseButton>
      </template>
    </BaseModal>
  </BaseSection>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import Sortable from 'sortablejs'
import { ElMessage, ElMessageBox } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import { addUpstream, deleteUpstream, deleteUpstreamModel, listUpstreams, reorderUpstreamModels, testUpstreamModel, toggleUpstreamModel, updateUpstream, updateUpstreamModels } from '@/api/upstreams'
import type { ModelEntry } from '@/api/upstreams'
import { fetchUpstreamModels } from '@/api/aggregated'
import { reloadConfig } from '@/api/common'
import { listGroups } from '@/api/groups'
import BaseCheckTag from '@/components/base/BaseCheckTag.vue'

const upstreams = ref<any[]>([])
const loading = ref(false)
const adding = ref(false)
const editing = ref(false)
const groupOptions = ref<{ name: string; description: string }[]>([])
const fetchingIds = ref<string[]>([])
const togglingIds = ref<string[]>([])
// 已配置模型（持久化，来自上游 models 字段，条目带可选协议覆盖）
const modelsByUpstream = reactive<Record<string, ModelEntry[]>>({})
// 拉取结果与勾选
const remoteModelsByUpstream = reactive<Record<string, string[]>>({})
const remoteChecked = reactive<Record<string, Record<string, boolean>>>({})
const fetchSearch = reactive<Record<string, string>>({})
const fetchPanelOpen = reactive<Record<string, boolean>>({})
// 单模型测试状态: status = idle | testing | ok | fail
const modelStatesByUpstream = reactive<Record<string, Record<string, { status: string; detail?: string; latency?: number }>>>({})
const testingModels = reactive<Record<string, string[]>>({})
// 列表折叠 + 全量测试
const COLLAPSE_THRESHOLD = 5
const modelExpanded = reactive<Record<string, boolean>>({})
const testingAll = reactive<Record<string, boolean>>({})
const testProgress = reactive<Record<string, string>>({})
// 批量选择
const modelSelected = reactive<Record<string, Record<string, boolean>>>({})
// 手动添加弹窗
const manualModal = reactive({ visible: false, uid: '', input: '', saving: false })

const addVisible = ref(false)
const editVisible = ref(false)

const addForm = reactive({
  id: '', name: '', base_url: '', api_keys_text: '', format: 'openai', groups: ['free'] as string[], probe_enabled: true, smart_retry: false,
})
const editForm = reactive({
  id: '', name: '', base_url: '', keys_text: '', format: 'openai', groups: ['free'] as string[], probe_enabled: true, smart_retry: false,
})

function parseKeys(text: string): string[] {
  return (text || '')
    .split('\n')
    .map((k: string) => k.trim())
    .filter((k: string) => k)
}

function buildEndpointPreview(baseUrl: string, path: string): string {
  const base = (baseUrl || '').trim().replace(/\/+$/, '')
  if (!base) return ''
  if (base.endsWith(path)) return base
  return `${base}${path}`
}

async function load() {
  loading.value = true
  try {
    const [res, groups]: any = await Promise.all([listUpstreams(), listGroups()])
    upstreams.value = res.upstreams
    groupOptions.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
    // 从持久化 models 字段回填已配置模型
    for (const u of res.upstreams) {
      modelsByUpstream[u.id] = u.models || []
      modelStatesByUpstream[u.id] = modelStatesByUpstream[u.id] || {}
      testingModels[u.id] = testingModels[u.id] || []
      modelExpanded[u.id] = modelExpanded[u.id] ?? false
      testingAll[u.id] = false
      modelSelected[u.id] = modelSelected[u.id] || {}
    }
  } finally {
    loading.value = false
  }
  initAllSortables()
}

function openAdd() {
  addForm.id = ''
  addForm.name = ''
  addForm.base_url = ''
  addForm.api_keys_text = ''
  addForm.format = 'openai'
  addForm.groups = ['free']
  addForm.probe_enabled = true
  addForm.smart_retry = false
  addVisible.value = true
}

function openEdit(u: any) {
  editForm.id = u.id
  editForm.name = u.name
  editForm.base_url = u.base_url
  editForm.keys_text = (u.keys || []).join('\n')
  editForm.format = u.format
  editForm.groups = (u.groups && u.groups.length ? [...u.groups] : [u.group || 'free'])
  editForm.probe_enabled = !!u.probe_enabled
  editForm.smart_retry = !!u.smart_retry
  editVisible.value = true
}

// ---------- 模型管理 ----------

async function openFetchPanel(u: any) {
  if (fetchPanelOpen[u.id]) {
    fetchPanelOpen[u.id] = false
    return
  }
  // 首次打开时拉取远端模型列表
  if (!remoteModelsByUpstream[u.id]) {
    fetchRemoteModels(u)
  }
  fetchPanelOpen[u.id] = true
}

async function fetchRemoteModels(u: any) {
  if (fetchingIds.value.includes(u.id)) return
  fetchingIds.value.push(u.id)
  try {
    const res: any = await fetchUpstreamModels(u.id)
    const models = res.models || []
    remoteModelsByUpstream[u.id] = models
    remoteChecked[u.id] = Object.fromEntries(models.map((m: string) => [m, false]))
    fetchSearch[u.id] = fetchSearch[u.id] || ''
    if (!models.length) ElMessage.warning('未拉取到模型列表（检查 Base URL / API Key 或服务商不支持 /v1/models）')
    else ElMessage.success(`获取到 ${models.length} 个模型`)
  } catch {
    ElMessage.error('获取模型列表失败')
  } finally {
    fetchingIds.value = fetchingIds.value.filter((id) => id !== u.id)
  }
}

function filteredRemoteModels(u: any): string[] {
  const q = (fetchSearch[u.id] || '').trim().toLowerCase()
  const list = remoteModelsByUpstream[u.id] || []
  if (!q) return list
  return list.filter((m) => m.toLowerCase().includes(q))
}

function selectedRemoteCount(u: any): number {
  const checked = remoteChecked[u.id] || {}
  return Object.values(checked).filter(Boolean).length
}

function toggleSelectAll(u: any) {
  const visible = filteredRemoteModels(u)
  if (!visible.length) return
  const checked = remoteChecked[u.id] || {}
  const allOn = visible.every((m) => checked[m])
  visible.forEach((m) => { checked[m] = !allOn })
}

async function handleJoin(u: any) {
  const checked = remoteChecked[u.id] || {}
  const picked = Object.keys(checked).filter((m) => checked[m])
  if (!picked.length) return
  const merged = mergeModels(modelsByUpstream[u.id], picked)
  if (merged.length === (modelsByUpstream[u.id] || []).length) {
    ElMessage.info('所选模型均已存在')
    return
  }
  try {
    await updateUpstreamModels(u.id, merged)
    modelsByUpstream[u.id] = merged
    ElMessage.success(`已加入 ${picked.length} 个模型`)
    fetchPanelOpen[u.id] = false
    remoteChecked[u.id] = {}
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存模型列表失败')
  }
}

function openManualModal(u: any) {
  manualModal.uid = u.id
  manualModal.input = ''
  manualModal.saving = false
  manualModal.visible = true
}

async function confirmManualAdd() {
  const names = (manualModal.input || '')
    .split(/[,，\s]+/)
    .map((n: string) => n.trim())
    .filter((n: string) => n)
  if (!names.length) {
    ElMessage.warning('请输入模型名')
    return
  }
  const merged = mergeModels(modelsByUpstream[manualModal.uid], names)
  manualModal.saving = true
  try {
    await updateUpstreamModels(manualModal.uid, merged)
    modelsByUpstream[manualModal.uid] = merged
    ElMessage.success(`已添加 ${names.length} 个模型`)
    manualModal.visible = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '添加失败')
  } finally {
    manualModal.saving = false
  }
}

function mergeModels(base: ModelEntry[] | undefined, added: string[]): ModelEntry[] {
  const map = new Map((base || []).map((e) => [e.name, e]))
  added.forEach((name) => {
    if (!map.has(name)) map.set(name, { name })
  })
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
}

async function setModelProtocol(u: any, modelName: string, protocol: string) {
  const effective = protocol === 'inherit' ? '' : protocol
  const list = modelsByUpstream[u.id] || []
  const newList = list.map((e) =>
    e.name === modelName ? (effective ? { name: e.name, protocol: effective as ModelEntry['protocol'] } : { name: e.name }) : e,
  )
  try {
    await updateUpstreamModels(u.id, newList)
    modelsByUpstream[u.id] = newList
    ElMessage.success(effective ? `模型「${modelName}」协议已设为 ${effective}` : `模型「${modelName}」已恢复继承源协议`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存协议失败')
  }
}

// ---------- 单模型启用/禁用（CH-019） ----------

const togglingModels = reactive<Record<string, boolean>>({})

async function handleToggleModel(u: any, modelName: string, enabled: boolean) {
  const k = `${u.id}:${modelName}`
  togglingModels[k] = true
  try {
    await toggleUpstreamModel(u.id, modelName, enabled)
    const list = modelsByUpstream[u.id] || []
    const idx = list.findIndex((e) => e.name === modelName)
    if (idx >= 0) modelsByUpstream[u.id][idx] = { ...list[idx], enabled }
    ElMessage.success(enabled ? `模型「${modelName}」已启用` : `模型「${modelName}」已禁用（不出现在 /v1/models，不参与路由与探测）`)
    await reloadConfig()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    togglingModels[k] = false
  }
}

// ---------- 模型拖拽排序（CH-019 二期：替代上移/下移按钮） ----------

const sortables: Record<string, Sortable> = {}

function initModelSortable(u: any) {
  const el = document.querySelector(`[data-sortable-upstream="${u.id}"]`) as HTMLElement | null
  if (!el) return
  sortables[u.id]?.destroy()
  sortables[u.id] = Sortable.create(el, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'drag-ghost',
    // 折叠状态下只显示前 N 行，拖拽会打乱全量顺序 → 折叠时禁用
    disabled: (modelsByUpstream[u.id] || []).length > COLLAPSE_THRESHOLD && !modelExpanded[u.id],
    onEnd: async (evt) => {
      const el = evt.from as HTMLElement
      const domOrder = Array.from(el.querySelectorAll('.model-row'))
        .map((n) => (n as HTMLElement).dataset.model || '')
        .filter(Boolean)
      const all = [...(modelsByUpstream[u.id] || [])]
      if (domOrder.length !== all.length) {
        // 折叠态下可见行少于全量行 → 不落库，交给下次展开后再拖
        await load()
        return
      }
      const byName = new Map(all.map((e) => [e.name, e]))
      const finalList = domOrder.map((n) => byName.get(n)).filter(Boolean) as ModelEntry[]
      // 先同步本地数据，避免 Vue 用旧数组回写 DOM
      modelsByUpstream[u.id] = finalList
      try {
        await reorderUpstreamModels(u.id, finalList.map((e) => e.name))
        await reloadConfig()
        ElMessage.success('模型顺序已保存')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.detail || '排序失败')
        await load()
      }
    },
  })
}

function initAllSortables() {
  nextTick(() => {
    upstreams.value.forEach((u: any) => initModelSortable(u))
  })
}

// ---------- 列表折叠 ----------

function visibleModels(u: any): ModelEntry[] {
  const all = modelsByUpstream[u.id] || []
  if (all.length > COLLAPSE_THRESHOLD && !modelExpanded[u.id]) {
    return all.slice(0, COLLAPSE_THRESHOLD)
  }
  return all
}

function toggleExpand(u: any) {
  modelExpanded[u.id] = !modelExpanded[u.id]
  // 折叠/展开会改变渲染行数，重建 Sortable 以刷新 disabled 状态
  nextTick(() => initModelSortable(u))
}

// ---------- 全量 / 批量测试 ----------

async function testAllModels(u: any) {
  await testModels(u, (modelsByUpstream[u.id] || []).map((e) => e.name))
}

async function batchTest(u: any) {
  await testModels(u, selectedModels(u))
}

async function testModels(u: any, models: string[]) {
  if (!models.length) {
    ElMessage.warning('暂无可测试的模型')
    return
  }
  if (testingAll[u.id]) return
  testingAll[u.id] = true
  modelExpanded[u.id] = true
  let okCount = 0
  let failCount = 0
  for (let i = 0; i < models.length; i++) {
    const m = models[i]
    testProgress[u.id] = `${i + 1}/${models.length}`
    testingModels[u.id].push(m)
    modelStatesByUpstream[u.id][m] = { status: 'testing' }
    const start = Date.now()
    try {
      const res: any = await testUpstreamModel(u.id, { model: m })
      if (res.ok) {
        okCount++
        modelStatesByUpstream[u.id][m] = { status: 'ok', latency: Date.now() - start, detail: res.content || '（无文本回复）' }
      } else {
        failCount++
        modelStatesByUpstream[u.id][m] = { status: 'fail', detail: res.error || '测试失败' }
      }
    } catch (e: any) {
      failCount++
      modelStatesByUpstream[u.id][m] = { status: 'fail', detail: e?.response?.data?.error || e?.response?.data?.detail || '测试请求失败' }
    } finally {
      testingModels[u.id] = testingModels[u.id].filter((x) => x !== m)
    }
  }
  delete testProgress[u.id]
  testingAll[u.id] = false
  ElMessageBox.alert(`上游「${u.name}」共 ${models.length} 个模型\n通过: ${okCount} 个\n失败: ${failCount} 个`, '测试完成', {
    confirmButtonText: '知道了',
  })
}

// ---------- 批量选择 / 删除 ----------

function allSelected(u: any): boolean {
  const all = modelsByUpstream[u.id] || []
  if (!all.length) return false
  const sel = modelSelected[u.id] || {}
  return all.every((e) => sel[e.name])
}

function toggleSelectAllModels(u: any) {
  const all = modelsByUpstream[u.id] || []
  const target = !allSelected(u)
  for (const e of all) {
    modelSelected[u.id][e.name] = target
  }
}

function selectedModelCount(u: any): number {
  const sel = modelSelected[u.id] || {}
  return Object.values(sel).filter(Boolean).length
}

function selectedModels(u: any): string[] {
  const all = modelsByUpstream[u.id] || []
  const sel = modelSelected[u.id] || {}
  return all.filter((e) => sel[e.name]).map((e) => e.name)
}

async function batchDelete(u: any) {
  const sel = selectedModels(u)
  if (!sel.length) return
  await ElMessageBox.confirm(`确定删除选中的 ${sel.length} 个模型吗？`, '批量删除确认', {
    type: 'warning',
  })
  const newList = (modelsByUpstream[u.id] || []).filter((e) => !sel.includes(e.name))
  try {
    await updateUpstreamModels(u.id, newList)
    modelsByUpstream[u.id] = newList
    modelSelected[u.id] = {}
    ElMessage.success(`已删除 ${sel.length} 个模型`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '批量删除失败')
  }
}

// ---------- 单模型测试 ----------

function isTesting(u: any, m: string): boolean {
  return (testingModels[u.id] || []).includes(m)
}

function modelState(u: any, m: string): { status: string; detail?: string; latency?: number } | undefined {
  return modelStatesByUpstream[u.id]?.[m]
}

function modelStateBadge(u: any, m: string): 'default' | 'blue' | 'green' | 'red' | 'gray' {
  const s = modelState(u, m)?.status
  if (s === 'ok') return 'green'
  if (s === 'fail') return 'red'
  if (s === 'testing') return 'blue'
  return 'gray'
}

function modelStateText(u: any, m: string): string {
  const s = modelState(u, m)
  if (!s || s.status === 'idle') return '未测试'
  if (s.status === 'testing') return '测试中'
  if (s.status === 'ok') return `通过 ${s.latency ?? ''}ms`
  return '失败'
}

function modelStateDetail(u: any, m: string): string {
  const s = modelState(u, m)
  return s?.detail || ''
}

async function testModel(u: any, m: string) {
  if (isTesting(u, m)) return
  testingModels[u.id].push(m)
  modelStatesByUpstream[u.id][m] = { status: 'testing' }
  const start = Date.now()
  try {
    const res: any = await testUpstreamModel(u.id, { model: m })
    const latency = Date.now() - start
    if (res.ok) {
      modelStatesByUpstream[u.id][m] = { status: 'ok', latency, detail: res.content || '（无文本回复）' }
      ElMessageBox.alert(`模型: ${m}\n耗时: ${latency} ms\n\n回复: ${res.content}`, `模型测试成功（${u.name}）`, {
        confirmButtonText: '知道了',
      })
    } else {
      modelStatesByUpstream[u.id][m] = { status: 'fail', detail: res.error || '测试失败' }
      ElMessage.error(res.error || '测试失败')
    }
  } catch (e: any) {
    modelStatesByUpstream[u.id][m] = { status: 'fail', detail: e?.response?.data?.error || e?.response?.data?.detail || '测试请求失败' }
    ElMessage.error(e?.response?.data?.error || e?.response?.data?.detail || '测试请求失败')
  } finally {
    testingModels[u.id] = testingModels[u.id].filter((x) => x !== m)
  }
}

async function removeModel(u: any, m: string) {
  await ElMessageBox.confirm(`确定从上游「${u.name}」移除模型「${m}」吗？`, '移除确认', {
    type: 'warning',
  })
  try {
    await deleteUpstreamModel(u.id, m)
    modelsByUpstream[u.id] = (modelsByUpstream[u.id] || []).filter((x) => x.name !== m)
    delete modelStatesByUpstream[u.id][m]
    ElMessage.success(`已移除模型「${m}」`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '移除失败')
  }
}

async function handleToggle(u: any, val: boolean) {
  togglingIds.value.push(u.id)
  try {
    await updateUpstream(u.id, { enabled: val })
    u.enabled = val
    ElMessage.success(val ? `上游源「${u.name}」已启用` : `上游源「${u.name}」已禁用`)
    await reloadConfig()
  } catch {
    ElMessage.error('状态更新失败')
  } finally {
    togglingIds.value = togglingIds.value.filter((id) => id !== u.id)
  }
}

async function handleDelete(u: any) {
  await ElMessageBox.confirm(`确定删除上游源「${u.name}」吗？删除后引用它的路由候选将失效。`, '删除确认', {
    type: 'warning',
  })
  await deleteUpstream(u.id)
  ElMessage.success('已删除')
  await reloadConfig()
  load()
}

async function handleAdd() {
  const keys = parseKeys(addForm.api_keys_text)
  if (!addForm.id || !addForm.name || !addForm.base_url || !keys.length) {
    ElMessage.warning('ID、名称、Base URL、API Key 均为必填')
    return
  }
  adding.value = true
  try {
    await addUpstream({
      id: addForm.id,
      name: addForm.name,
      base_url: addForm.base_url,
      api_keys: keys,
      format: addForm.format,
      groups: addForm.groups.length ? addForm.groups : ['free'],
      probe_enabled: addForm.probe_enabled,
      smart_retry: addForm.smart_retry,
    })
    ElMessage.success(`上游源 ${addForm.id} 添加成功`)
    addVisible.value = false
    await reloadConfig()
    load()
  } finally {
    adding.value = false
  }
}

async function handleEditSave() {
  if (!editForm.name || !editForm.base_url) {
    ElMessage.warning('名称和 Base URL 为必填')
    return
  }
  editing.value = true
  try {
    const payload: Record<string, unknown> = {
      name: editForm.name,
      base_url: editForm.base_url,
      format: editForm.format,
      groups: editForm.groups.length ? editForm.groups : ['free'],
      probe_enabled: editForm.probe_enabled,
      smart_retry: editForm.smart_retry,
    }
    const keys = parseKeys(editForm.keys_text)
    if (keys.length) payload.api_keys = keys
    await updateUpstream(editForm.id, payload)
    ElMessage.success(`上游源「${editForm.name}」修改成功`)
    editVisible.value = false
    await reloadConfig()
    load()
  } finally {
    editing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
.upstream-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--bg-base);
}
.upstream-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 12px;
  flex-wrap: wrap;
}
.upstream-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.upstream-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.upstream-card.is-disabled {
  opacity: 0.55;
  background: var(--bg-elevated);
}
.upstream-name {
  font-weight: 600;
  font-size: 1.05rem;
}
.upstream-meta {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.model-section {
  margin-top: 12px;
  padding: 10px;
  background: var(--bg-base);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}
.model-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.model-title {
  font-weight: 600;
  font-size: 0.9rem;
}
.model-count {
  font-weight: 400;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-left: 4px;
}
.model-ops {
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-list {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}
.model-batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 10px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-subtle);
}
.batch-count {
  font-size: 0.8rem;
  color: var(--text-secondary);
}
.batch-ops {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.model-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-base);
}
.model-row + .model-row {
  border-top: 1px solid var(--border-subtle);
}
.model-row:hover {
  background: var(--bg-hover);
}
.model-row.model-disabled .model-name {
  color: var(--text-tertiary);
  text-decoration: line-through;
}
.model-row-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.drag-handle {
  cursor: grab;
  color: var(--text-tertiary);
  font-size: 1rem;
  user-select: none;
  flex-shrink: 0;
}
.drag-handle:active {
  cursor: grabbing;
}
.drag-handle.is-disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.drag-ghost {
  opacity: 0.4;
}
.model-name {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.model-detail {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-detail.detail-fail {
  color: var(--accent-red);
  max-width: 300px;
  white-space: normal;
  overflow: visible;
  line-height: 1.5;
}
.model-expand-bar {
  display: flex;
  justify-content: center;
  padding: 6px 0;
  border-top: 1px solid var(--border-subtle);
}
.model-empty {
  padding: 8px 4px;
}
.url-preview {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--bg-elevated);
  border-radius: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.7;
}
.url-preview code {
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text-primary);
  word-break: break-all;
}
.fetch-panel {
  margin-top: 8px;
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-elevated);
}
.fetch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.fetch-title {
  font-weight: 600;
  font-size: 0.85rem;
}
.fetch-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 140px;
  overflow-y: auto;
}
.fetch-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}
.fetch-count {
  font-size: 0.8rem;
  color: var(--text-secondary);
}
</style>
