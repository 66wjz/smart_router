<template>
  <div>
    <!-- 一、疑似同一模型（归一化建议） -->
    <BaseSection v-if="suggestions.length" variant="card" title="疑似同一模型（建议合并）">
      <el-alert
        title="系统按「去前缀 + 忽略大小写 + 忽略 . _ 差异」识别出下列模型可能其实是同一个。确认后会合成一个聚合名，客户端用该名字即可自动跨源兜底。"
        type="warning"
        :closable="false"
        style="margin-bottom: 16px"
      />

      <div v-for="s in suggestions" :key="s.normalized" class="suggest-card">
        <div class="suggest-head">
          <div class="suggest-title">
            <BaseBadge variant="amber">建议聚合名</BaseBadge>
            <code class="group-model">{{ s.suggested_name }}</code>
            <BaseBadge variant="gray">{{ s.members.length }} 个成员</BaseBadge>
          </div>
          <BaseButton variant="primary" size="sm" :disabled="merging === s.normalized" @click="mergeSuggestion(s)">
            {{ merging === s.normalized ? '合并中…' : '一键合并' }}
          </BaseButton>
        </div>
        <div class="suggest-members">
          <span v-for="m in s.members" :key="m.upstream + m.model" class="member-chip">
            <span class="chip-src">{{ m.upstream_name }}</span>
            <code>{{ m.model }}</code>
          </span>
        </div>
      </div>
    </BaseSection>

    <!-- 二、聚合组列表 -->
    <BaseSection variant="card" title="模型聚合（跨源自动兜底）">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="loadAll">刷新</BaseButton>
      </template>

      <el-alert
        title="同一个模型名分布在多个上游源时，默认自动互为候选（按源顺序兜底）。不同源里模型名不一致（如 buddy/deepseek-v4.1-flash 与 loomy/DeepSeek-V4.1-Flash）可用「编辑成员」手动归到同一个聚合名下。"
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
      />

      <div v-if="!groups.length" class="empty-tip">
        <el-text type="info">当前没有聚合组。同一模型名只存在于一个源时不构成聚合；异名模型可在下方手动创建。</el-text>
      </div>

      <div v-for="g in groups" :key="g.model" class="group-card">
        <div class="group-head">
          <div class="group-title">
            <code class="group-model">{{ g.model }}</code>
            <BaseBadge :variant="g.configured ? 'blue' : 'gray'">
              {{ g.configured ? '已手动配置' : '自动发现' }}
            </BaseBadge>
            <BaseBadge :variant="g.members.length > 1 ? 'green' : 'amber'">
              {{ g.enabled ? `${g.members.length} 源聚合` : '聚合已关闭' }}
            </BaseBadge>
            <BaseBadge :variant="probeBadge(g).variant">{{ probeBadge(g).text }}</BaseBadge>
          </div>
          <div class="group-ops">
            <span class="op-label">启用聚合</span>
            <el-switch
              :model-value="g.enabled"
              size="small"
              :disabled="savingModel === g.model"
              @change="(val: boolean | string | number) => toggleGroup(g, Boolean(val))"
            />
            <BaseButton v-if="g.configured" variant="ghost" size="sm" :disabled="savingModel === g.model" @click="resetGroup(g)">
              恢复自动
            </BaseButton>
            <BaseButton variant="ghost" size="sm" @click="openProbe(g)">探测设置</BaseButton>
            <BaseButton variant="primary" size="sm" :disabled="savingModel === g.model" @click="openEdit(g)">
              {{ savingModel === g.model ? '保存中…' : '编辑成员' }}
            </BaseButton>
          </div>
        </div>

        <!-- 生效链路：源 · 真实模型名 -->
        <div class="source-flow">
          <template v-for="(m, i) in g.members" :key="m.upstream + m.model">
            <span class="source-chip" :class="{ 'is-first': i === 0 }">
              <span class="chip-index">{{ i + 1 }}</span>
              <span class="chip-src">{{ m.upstream }}</span>
              <code class="chip-model">{{ m.model }}</code>
              <el-text v-if="i === 0" type="success" size="small">首选</el-text>
              <el-text v-else-if="i === g.members.length - 1" type="info" size="small">兜底</el-text>
            </span>
            <span v-if="i < g.members.length - 1" class="arrow">→</span>
          </template>
          <span v-if="!g.members.length" class="empty-tip"><el-text type="warning">没有任何可用成员</el-text></span>
        </div>

        <div v-if="!g.enabled" class="group-warn">
          <el-text type="warning" size="small">聚合已关闭：请求该名字时只走第一个可用成员，不做跨源兜底。</el-text>
        </div>
      </div>

      <div class="create-bar">
        <BaseButton variant="ghost" size="sm" @click="openCreate">+ 新建聚合（可含异名模型）</BaseButton>
      </div>
    </BaseSection>

    <!-- 探测计划（全局去重） -->
    <BaseSection v-if="plan.units.length" variant="card" title="探测计划（全局去重）" style="margin-top: 16px">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="loadProbeData">刷新</BaseButton>
      </template>
      <el-alert
        :title="`共 ${plan.summary.unit_count} 个探测单元（按「上游源 × 真实模型」去重，已省掉 ${plan.summary.dedup_saved} 次重复探测）· 每天约 ${plan.summary.daily_requests.toLocaleString()} 次探测请求`"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-table :data="plan.units" size="small" stripe>
        <el-table-column prop="upstream_name" label="上游源" width="140" />
        <el-table-column prop="model" label="真实模型名" min-width="220" show-overflow-tooltip />
        <el-table-column label="被哪些组引用" min-width="200">
          <template #default="{ row }">
            <BaseBadge v-for="g in row.groups" :key="g" variant="blue" style="margin-right: 4px">{{ g }}</BaseBadge>
            <el-text v-if="!row.groups.length" type="info" size="small">仅路由规则/别名</el-text>
          </template>
        </el-table-column>
        <el-table-column label="间隔" width="90">
          <template #default="{ row }">{{ row.interval }}s</template>
        </el-table-column>
        <el-table-column label="最近延迟" width="100">
          <template #default="{ row }">{{ row.latency != null ? `${row.latency}s` : 'N/A' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <BaseBadge :variant="row.status === 'ok' ? 'green' : row.status === 'down' ? 'red' : 'gray'">
              {{ row.status === 'ok' ? '可用' : row.status === 'down' ? '不可用' : '未知' }}
            </BaseBadge>
            <BaseBadge v-if="!row.active_now" variant="amber" style="margin-left: 4px">时段外</BaseBadge>
            <BaseBadge v-else-if="row.stale" variant="gray" style="margin-left: 4px">数据陈旧</BaseBadge>
          </template>
        </el-table-column>
      </el-table>
    </BaseSection>

    <!-- 三、手写聚合名（原有机制，候选来自路由规则） -->
    <BaseSection variant="card" title="聚合模型名（手写规则聚合）" style="margin-top: 16px">
      <el-alert
        title="这里的名字是客户端请求时使用的统一模型名，候选来自「路由规则」页配置的候选列表；与上面的模型聚合是两套独立机制。"
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
      />
      <div v-if="names.length" style="margin-bottom: 16px">
        <BaseBadge v-for="n in names" :key="n" variant="default" style="margin: 4px">{{ n }}</BaseBadge>
      </div>
      <el-form label-width="120px" style="max-width: 560px">
        <el-form-item label="聚合模型名">
          <BaseInput v-model="namesText" placeholder="逗号分隔，如 smart-latest, smart-chat" />
        </el-form-item>
        <el-form-item>
          <BaseButton variant="primary" :disabled="saving" @click="handleSaveNames">
            {{ saving ? '保存中...' : '保存' }}
          </BaseButton>
        </el-form-item>
      </el-form>
    </BaseSection>

    <!-- 探测设置弹窗 -->
    <BaseModal v-model:visible="probeVisible" :title="`探测设置：${probeModel}`" size="large">
      <el-alert
        title="只影响本聚合组的探测节奏与排序；探测对象是全局去重后的单元，多组共用同一模型时不会重复探测。"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-form :model="probeForm" label-width="130px">
        <el-form-item label="启用定时探测">
          <el-switch v-model="probeForm.enabled" />
          <el-text type="info" size="small" style="margin-left: 10px">
            {{ probeForm.enabled ? '按下方节奏探测，结果用于本组排序' : '关闭后本组不新增探测单元（已存在的仍可能被其他组复用）' }}
          </el-text>
        </el-form-item>

        <el-form-item label="探测间隔（秒）">
          <el-input-number
            v-model="probeForm.interval_seconds"
            :min="0"
            :step="10"
            style="width: 200px"
          />
          <el-text type="info" size="small" style="margin-left: 10px">
            0 = 跟随全局 {{ globalInterval }}s；多组共用同一单元时取最小值
          </el-text>
        </el-form-item>

        <el-form-item label="慢阈值（秒）">
          <el-input-number
            v-model="probeForm.slow_threshold_seconds"
            :min="0"
            :step="1"
            style="width: 200px"
          />
          <el-text type="info" size="small" style="margin-left: 10px">0 = 跟随全局；超过此延迟的成员排到后面</el-text>
        </el-form-item>

        <el-form-item label="排序模式">
          <el-radio-group v-model="probeForm.sort_mode">
            <el-radio value="stable">稳定优先（我定的顺序，慢的沉底）</el-radio>
            <el-radio value="latency">速度优先（按实时延迟排序）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-divider content-position="left">探测时段</el-divider>

        <el-form-item label="时段模式">
          <el-radio-group v-model="probeForm.schedule.mode">
            <el-radio value="always">全天候</el-radio>
            <el-radio value="window">仅指定时段</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="probeForm.schedule.mode === 'window'">
          <el-form-item label="星期">
            <el-checkbox-group v-model="probeForm.schedule.days">
              <el-checkbox v-for="d in DAY_OPTIONS" :key="d.value" :value="d.value">{{ d.label }}</el-checkbox>
            </el-checkbox-group>
            <div class="hint">不勾选 = 每天都探测</div>
          </el-form-item>

          <el-form-item label="时段窗口">
            <div class="window-list">
              <div v-for="(w, i) in probeForm.schedule.windows" :key="i" class="window-row">
                <el-time-select v-model="w.start" start="00:00" end="23:30" step="00:30" placeholder="开始" style="width: 130px" />
                <span class="sep">→</span>
                <el-time-select v-model="w.end" start="00:30" end="23:59" step="00:30" placeholder="结束" style="width: 130px" />
                <BaseButton variant="danger" size="sm" @click="probeForm.schedule.windows.splice(i, 1)">删除</BaseButton>
              </div>
              <BaseButton variant="ghost" size="sm" @click="addWindow">+ 添加时段</BaseButton>
              <div class="hint">
                例：08:00→23:00 表示夜间不探测；23:00→07:00 表示只在这个跨夜时段探测。窗口外保留最后一次结果并标记「时段外」。
              </div>
            </div>
          </el-form-item>

          <el-form-item label="快捷模板">
            <BaseButton variant="ghost" size="sm" @click="applyPreset('workday')">工作日全天</BaseButton>
            <BaseButton variant="ghost" size="sm" @click="applyPreset('daytime')">每天 08:00-23:00</BaseButton>
            <BaseButton variant="ghost" size="sm" @click="applyPreset('weekend')">仅周末</BaseButton>
          </el-form-item>
        </template>
      </el-form>

      <el-alert
        v-if="probeMemberCount"
        :title="`本组 ${probeMemberCount} 个成员；具体去重结果见下方「探测计划」表。`"
        type="info"
        :closable="false"
      />

      <template #footer>
        <BaseButton variant="ghost" @click="probeVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="savingProbe" @click="saveProbe">
          {{ savingProbe ? '保存中…' : '保存' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 编辑/新建弹窗 -->
    <BaseModal v-model:visible="editVisible" :title="editMode === 'create' ? '新建聚合' : `编辑聚合：${editModel}`" size="large">
      <el-alert
        title="拖动调整优先级（从上到下即请求尝试顺序）；每个成员可指定该源里的真实模型名，因此不同源的异名模型也能聚合到一起。"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
      />

      <el-form label-width="90px" style="margin-bottom: 12px">
        <el-form-item label="聚合名" required>
          <BaseInput v-model="editModel" :disabled="editMode === 'edit'" placeholder="客户端请求时使用的名字，如 deepseek-v4-1-flash" />
        </el-form-item>
      </el-form>

      <div ref="dragListRef" class="drag-list">
        <div v-for="item in editItems" :key="item.upstream + '|' + item.model" class="drag-item">
          <span class="drag-handle" role="button" tabindex="0" aria-label="拖动调整顺序" title="拖动调整顺序">⠿</span>
          <span class="drag-upstream">{{ item.upstream }}</span>
          <el-select
            v-model="item.model"
            filterable
            allow-create
            default-first-option
            size="small"
            class="drag-model-select"
            placeholder="该源里的真实模型名"
          >
            <el-option v-for="m in modelsOf(item.upstream)" :key="m" :label="m" :value="m" />
          </el-select>
          <el-input-number v-model="item.weight" :min="1" :max="10" size="small" style="width: 90px" />
          <BaseButton variant="danger" size="sm" @click="removeItem(item)">移除</BaseButton>
        </div>
      </div>
      <el-empty v-if="!editItems.length" description="还没有成员，请在下方添加" :image-size="50" />

      <div class="add-row">
        <el-select v-model="addUpstream" placeholder="选择上游源" size="small" style="width: 200px" @change="onAddUpstreamChange">
          <el-option v-for="u in upstreams" :key="u.id" :label="u.name || u.id" :value="u.id" />
        </el-select>
        <el-select
          v-model="addModel"
          filterable
          allow-create
          default-first-option
          size="small"
          placeholder="选择/输入真实模型名"
          style="width: 300px"
        >
          <el-option v-for="m in modelsOf(addUpstream)" :key="m" :label="m" :value="m" />
        </el-select>
        <BaseButton variant="primary" size="sm" @click="addItem">+ 添加成员</BaseButton>
      </div>

      <template #footer>
        <BaseButton variant="ghost" @click="editVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="savingModel === editModel" @click="saveEdit">
          {{ savingModel === editModel ? '保存中…' : '保存' }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import { getAggregatedNames, saveAggregatedNames } from '@/api/aggregated'
import {
  deleteModelGroup,
  getProbePlan,
  listGroupSuggestions,
  listModelGroups,
  listProbeConfigs,
  listSourceModels,
  saveGroupProbe,
  saveModelGroup,
} from '@/api/model_groups'
import { listUpstreams } from '@/api/upstreams'
import { getProbeConfig } from '@/api/settings'
import { reloadConfig } from '@/api/common'

// ---------- 原有：手写聚合名 ----------
const names = ref<string[]>([])
const namesText = ref('')
const saving = ref(false)

// ---------- 聚合组 ----------
const groups = ref<any[]>([])
const suggestions = ref<any[]>([])
const upstreams = ref<any[]>([])
const savingModel = ref('')
const merging = ref('')

// ---------- 探测（CH-021） ----------
const probeConfigs = ref<Record<string, any>>({})
const plan = ref<{ summary: any; units: any[] }>({
  summary: { unit_count: 0, member_refs: 0, dedup_saved: 0, daily_requests: 0, global_interval: 120 },
  units: [],
})
const globalInterval = ref(120)

const probeVisible = ref(false)
const probeModel = ref('')
const probeMemberCount = ref(0)
const savingProbe = ref(false)
const probeForm = reactive<any>({
  enabled: false,
  interval_seconds: null,
  slow_threshold_seconds: null,
  sort_mode: 'stable',
  schedule: { mode: 'always', days: [], windows: [] },
})

const DAY_OPTIONS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
]

type BadgeVariant = 'default' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'gray'

function probeBadge(g: any): { text: string; variant: BadgeVariant } {
  const cfg = probeConfigs.value[g.model]
  if (!cfg || !cfg.enabled) return { text: '探测: 关', variant: 'gray' }
  const sched = cfg.schedule?.mode === 'window' ? ' · 限时段' : ''
  const iv = cfg.raw?.interval_seconds ? `${cfg.interval_seconds}s` : `全局${cfg.interval_seconds}s`
  return { text: `探测: 开 · ${iv}${sched}`, variant: 'green' }
}

async function loadProbeData() {
  const [cfgs, pl, gc]: any = await Promise.all([
    listProbeConfigs(),
    getProbePlan(),
    getProbeConfig().catch(() => ({ interval_seconds: 120 })),
  ])
  probeConfigs.value = cfgs.configs || {}
  plan.value = {
    summary: pl.summary || plan.value.summary,
    units: pl.units || [],
  }
  globalInterval.value = gc?.interval_seconds || 120
}

function openProbe(g: any) {
  probeModel.value = g.model
  probeMemberCount.value = (g.members || []).length
  const cfg = probeConfigs.value[g.model]
  const raw = cfg?.raw || {}
  probeForm.enabled = Boolean(cfg?.enabled)
  // 0 在 UI 上代表「跟随全局」，落库时转成 null
  probeForm.interval_seconds = raw.interval_seconds ?? 0
  probeForm.slow_threshold_seconds = raw.slow_threshold_seconds ?? 0
  probeForm.sort_mode = cfg?.sort_mode || 'stable'
  const sched = cfg?.schedule || { mode: 'always' }
  probeForm.schedule = {
    mode: sched.mode || 'always',
    days: [...(sched.days || [])],
    windows: (sched.windows || []).map((w: any) => ({ start: w.start, end: w.end })),
  }
  probeVisible.value = true
}

function addWindow() {
  probeForm.schedule.windows.push({ start: '08:00', end: '23:00' })
}

function applyPreset(kind: string) {
  probeForm.schedule.mode = 'window'
  if (kind === 'workday') {
    probeForm.schedule.days = [1, 2, 3, 4, 5]
    probeForm.schedule.windows = []
  } else if (kind === 'daytime') {
    probeForm.schedule.days = []
    probeForm.schedule.windows = [{ start: '08:00', end: '23:00' }]
  } else if (kind === 'weekend') {
    probeForm.schedule.days = [6, 7]
    probeForm.schedule.windows = []
  }
}

async function saveProbe() {
  const sched = probeForm.schedule
  if (sched.mode === 'window') {
    for (const w of sched.windows) {
      if (!w.start || !w.end) {
        ElMessage.warning('时段窗口需要同时填写开始和结束')
        return
      }
      if (w.start === w.end) {
        ElMessage.warning('时段的开始与结束不能相同')
        return
      }
    }
  }
  savingProbe.value = true
  try {
    await saveGroupProbe(probeModel.value, {
      enabled: probeForm.enabled,
      interval_seconds: probeForm.interval_seconds ? Number(probeForm.interval_seconds) : null,
      slow_threshold_seconds: probeForm.slow_threshold_seconds ? Number(probeForm.slow_threshold_seconds) : null,
      sort_mode: probeForm.sort_mode,
      schedule: {
        mode: sched.mode,
        days: sched.mode === 'window' ? sched.days : [],
        windows: sched.mode === 'window' ? sched.windows : [],
      },
    })
    ElMessage.success('探测设置已保存')
    probeVisible.value = false
    await reloadConfig()
    await loadProbeData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingProbe.value = false
  }
}

// 上游源 → 模型名列表缓存
const sourceModels = reactive<Record<string, string[]>>({})

const editVisible = ref(false)
const editMode = ref<'create' | 'edit'>('edit')
const editModel = ref('')
const editItems = ref<{ upstream: string; model: string; weight: number }[]>([])
const dragListRef = ref<HTMLElement | null>(null)
let sortable: Sortable | null = null

const addUpstream = ref('')
const addModel = ref('')

function modelsOf(upstream: string): string[] {
  return sourceModels[upstream] || []
}

async function ensureSourceModels(upstream: string) {
  if (!upstream || sourceModels[upstream]) return
  try {
    const res: any = await listSourceModels(upstream)
    sourceModels[upstream] = (res.models || []).map((m: any) => m.name)
  } catch {
    sourceModels[upstream] = []
  }
}

async function loadAll() {
  const [g, s]: any = await Promise.all([listModelGroups(), listGroupSuggestions()])
  groups.value = g.groups || []
  suggestions.value = s.suggestions || []
  await loadProbeData()
}

async function loadUpstreams() {
  const res: any = await listUpstreams()
  upstreams.value = res.upstreams || []
}

// ---------- 建议合并 ----------
async function mergeSuggestion(s: any) {
  merging.value = s.normalized
  try {
    const members = s.members.map((m: any) => ({ upstream: m.upstream, model: m.model, weight: 1 }))
    await saveModelGroup(s.suggested_name, members, true)
    ElMessage.success(`已合并为聚合名「${s.suggested_name}」，共 ${members.length} 个成员`)
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '合并失败')
  } finally {
    merging.value = ''
  }
}

// ---------- 聚合组操作 ----------
async function toggleGroup(g: any, enabled: boolean) {
  savingModel.value = g.model
  try {
    const members = (g.members || []).map((m: any) => ({ upstream: m.upstream, model: m.model, weight: 1 }))
    await saveModelGroup(g.model, members, enabled)
    ElMessage.success(enabled ? `「${g.model}」已启用跨源聚合` : `「${g.model}」已关闭聚合（仅走首选成员）`)
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingModel.value = ''
  }
}

async function resetGroup(g: any) {
  await ElMessageBox.confirm(`确定对「${g.model}」恢复自动发现吗？手动配置将被删除。`, '恢复自动', { type: 'warning' })
  savingModel.value = g.model
  try {
    await deleteModelGroup(g.model)
    ElMessage.success('已恢复自动发现')
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    savingModel.value = ''
  }
}

function openEdit(g: any) {
  editMode.value = 'edit'
  editModel.value = g.model
  editItems.value = (g.members || []).map((m: any) => ({
    upstream: m.upstream,
    model: m.model || g.model,
    weight: 1,
  }))
  editItems.value.forEach((it) => ensureSourceModels(it.upstream))
  editVisible.value = true
  nextTick(initSortable)
}

function openCreate() {
  editMode.value = 'create'
  editModel.value = ''
  editItems.value = []
  addUpstream.value = upstreams.value[0]?.id || ''
  addModel.value = ''
  ensureSourceModels(addUpstream.value)
  editVisible.value = true
  nextTick(initSortable)
}

function onAddUpstreamChange() {
  addModel.value = ''
  ensureSourceModels(addUpstream.value)
}

function addItem() {
  if (!addUpstream.value || !addModel.value) {
    ElMessage.warning('请选择上游源并填写模型名')
    return
  }
  const dup = editItems.value.some((x) => x.upstream === addUpstream.value && x.model === addModel.value)
  if (dup) {
    ElMessage.info('该成员已存在')
    return
  }
  editItems.value.push({ upstream: addUpstream.value, model: addModel.value, weight: 1 })
  addModel.value = ''
}

function removeItem(item: any) {
  editItems.value = editItems.value.filter((x) => !(x.upstream === item.upstream && x.model === item.model))
}

function initSortable() {
  if (!dragListRef.value) return
  sortable?.destroy()
  sortable = Sortable.create(dragListRef.value, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'drag-ghost',
    fallbackTolerance: 3,
    group: { name: 'agg-members', pull: false, put: false },
    onEnd: (evt) => {
      const from = evt.oldIndex ?? -1
      const to = evt.newIndex ?? -1
      if (from < 0 || to < 0 || from === to) return
      const moved = editItems.value.splice(from, 1)[0]
      editItems.value.splice(to, 0, moved)
    },
  })
}

async function saveEdit() {
  const name = (editModel.value || '').trim()
  if (!name) {
    ElMessage.warning('聚合名为必填')
    return
  }
  if (!editItems.value.length) {
    ElMessage.warning('至少添加一个成员')
    return
  }
  savingModel.value = name
  try {
    await saveModelGroup(
      name,
      editItems.value.map((x) => ({ upstream: x.upstream, model: x.model, weight: x.weight })),
      true,
    )
    ElMessage.success('聚合配置已保存')
    editVisible.value = false
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingModel.value = ''
  }
}

// ---------- 原有：手写聚合名 ----------
async function loadNames() {
  const res: any = await getAggregatedNames()
  names.value = res.names || []
  namesText.value = (res.names || []).join(', ')
}

async function handleSaveNames() {
  const newNames = namesText.value.split(',').map((n) => n.trim()).filter(Boolean)
  saving.value = true
  try {
    await saveAggregatedNames(newNames)
    ElMessage.success('聚合模型名已更新')
    await reloadConfig()
    loadNames()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadNames(), loadUpstreams()])
  await loadAll()
})
</script>

<style scoped>
.empty-tip {
  padding: 8px 0;
}
.hint {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 4px;
  line-height: 1.5;
}
.window-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.window-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.window-row .sep {
  color: var(--text-tertiary);
}
/* 建议合并 */
.suggest-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--bg-base);
}
.suggest-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.suggest-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.suggest-members {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.member-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-hover);
  font-size: 0.78rem;
}
.member-chip code {
  font-family: var(--font-mono, ui-monospace, monospace);
}
/* 聚合组卡片 */
.group-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 12px;
  background: var(--bg-base);
}
.group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.group-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.95rem;
  font-weight: 600;
}
.group-ops {
  display: flex;
  align-items: center;
  gap: 8px;
}
.op-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}
.source-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.source-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-hover);
  font-size: 0.8rem;
}
.source-chip.is-first {
  background: var(--accent-green-muted, rgba(103, 194, 58, 0.12));
}
.chip-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-base);
  font-size: 0.7rem;
}
.chip-src {
  color: var(--text-secondary, var(--text-tertiary));
}
.chip-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.75rem;
}
.arrow {
  color: var(--text-tertiary);
  font-size: 0.85rem;
}
.group-warn {
  margin-top: 8px;
}
.create-bar {
  margin-top: 12px;
}
/* 编辑弹窗 */
.drag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.drag-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-base);
}
.drag-handle {
  cursor: grab;
  color: var(--text-tertiary);
  font-size: 1rem;
  user-select: none;
}
.drag-upstream {
  font-size: 0.82rem;
  color: var(--text-secondary, var(--text-tertiary));
  min-width: 110px;
}
.drag-model-select {
  flex: 1;
  min-width: 240px;
}
.drag-ghost {
  opacity: 0.35;
  background: var(--accent-blue-muted, rgba(64, 158, 255, 0.12)) !important;
  border: 1px dashed var(--accent-blue, #409eff) !important;
}
.drag-item.sortable-chosen {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
}
/* 插入位置指示线 */
.drag-item.sortable-ghost {
  border-top: 2px solid var(--accent-blue, #409eff) !important;
}
.add-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
</style>
