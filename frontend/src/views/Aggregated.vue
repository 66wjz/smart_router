<template>
  <div>
    <el-tabs v-model="activeTab" class="agg-tabs">
      <!-- ==================== 聚合组 ==================== -->
      <el-tab-pane name="groups">
        <template #label>
          <span class="tab-label">聚合组 <span class="tab-count">{{ aggregations.length }}</span></span>
        </template>

        <!--
          CH-045：原「疑似同一模型（建议合并）」改名为「聚合模型发现」，
          与聚合模型同一个列表骨架：标题 + 右上刷新 + 常驻工具条（全选/批量合并）
          + 卡片条目 + 底部统一分页。
        -->
        <ListPage
          v-if="suggestions.length"
          title="聚合模型发现"
          :page="suggPage"
          :page-size="suggPageSize"
          :total="suggestions.length"
          :page-sizes="[10, 20, 50]"
          @update:page="suggPage = $event"
          @update:page-size="suggPageSize = $event"
        >
          <template #actions>
            <BaseButton variant="ghost" size="sm" @click="loadAll">刷新</BaseButton>
          </template>

          <template #notice>
            <BaseNotice variant="warning"
              text="系统按「去前缀 + 忽略大小写 + 忽略 . _ 差异」识别出下列模型可能其实是同一个。确认后会合成一个聚合名，客户端用该名字即可自动跨源兜底。" />
          </template>

          <template #toolbar>
            <ListToolbar
              :count="selectedSuggestions.length"
              :total="suggestions.length"
              :actions="suggBatchActions"
              selectable
              :all-checked="allSuggChecked"
              :indeterminate="suggIndeterminate"
              @toggle-all="toggleAllSuggestions"
              @clear="clearSuggSelection"
            />
          </template>

          <EntityCard
            v-for="s in pagedSuggestions"
            :key="s.normalized"
            selectable
            :checked="selectedSuggestions.includes(s.normalized)"
            @update:checked="(v: boolean) => toggleSuggChecked(s.normalized, v)"
          >
            <template #title>
              <BaseBadge variant="amber">建议聚合名</BaseBadge>
              <code class="group-model">{{ s.suggested_name }}</code>
              <BaseBadge variant="gray">{{ s.members.length }} 个成员</BaseBadge>
            </template>
            <template #actions>
              <BaseButton variant="primary" size="sm" :disabled="merging === s.normalized"
                @click="mergeSuggestion(s)">
                {{ merging === s.normalized ? '合并中…' : '一键合并' }}
              </BaseButton>
            </template>
            <!-- CH-043：成员集合统一走 ChipFlow（CH-044 起平铺，不在卡片内分页） -->
            <ChipFlow :items="s.members" />
          </EntityCard>
        </ListPage>

        <!--
          CH-044：聚合模型本质是「条目为卡片的列表」。
          标题 + 右上操作 + 批量条 + 卡片区 + 分页 由 ListPage 统一承载，
          分页归列表（页面底部），不再塞进每张卡片内部。
        -->
        <ListPage
          title="聚合模型"
          style="margin-top: 16px"
          :page="aggPage"
          :page-size="aggPageSize"
          :total="filteredAggs.length"
          :page-sizes="[10, 20, 50]"
          @update:page="aggPage = $event"
          @update:page-size="aggPageSize = $event"
        >
          <template #actions>
            <BaseButton variant="ghost" size="sm" @click="loadAll">刷新</BaseButton>
            <BaseButton variant="primary" size="sm" @click="openCreate">+ 新建聚合</BaseButton>
          </template>

          <template #notice>
            <BaseNotice
              text="两类聚合统一管理：固定成员（可跨源、可异名）由你指定候选；规则聚合的候选由「路由规则」页在运行时按请求内容匹配，探测时会覆盖全部规则候选的并集。" />
          </template>

          <template #filters>
            <FilterBar @search="aggPage = 1" @reset="resetAggFilter">
              <FilterField label="聚合名" :width="260">
                <BaseInput
                  v-model="aggKeyword"
                  size="sm"
                  placeholder="输入聚合名过滤"
                  @keydown.enter="aggPage = 1"
                />
              </FilterField>
              <FilterField label="类型" :width="140">
                <el-select v-model="aggKind" size="small" clearable placeholder="全部">
                  <el-option label="固定成员" value="static" />
                  <el-option label="规则匹配" value="rule" />
                </el-select>
              </FilterField>
              <FilterField label="状态" :width="130">
                <el-select v-model="aggEnabled" size="small" clearable placeholder="全部">
                  <el-option label="启用" :value="true" />
                  <el-option label="已关闭" :value="false" />
                </el-select>
              </FilterField>
            </FilterBar>
          </template>

          <template #toolbar>
            <ListToolbar
              :count="selectedAggs.length"
              :total="filteredAggs.length"
              :summary="`已启用 ${enabledAggCount} 个`"
              :actions="aggBatchActions"
              selectable
              :all-checked="allPageChecked"
              :indeterminate="pageIndeterminate"
              @toggle-all="toggleAllOnPage"
              @clear="clearAggSelection"
            />
          </template>

          <BaseEmptyState v-if="!aggregations.length" compact
            description="当前没有聚合。同一模型名只存在于一个源时不构成聚合；异名模型可手动创建。" />

          <div v-else class="agg-list">
            <AggregationCard
              v-for="g in pagedAggs"
              :key="g.name"
              :g="g"
              :saving="savingName === g.name"
              :checked="selectedAggs.includes(g.name)"
              @update:checked="(v: boolean) => toggleAggChecked(g.name, v)"
              @toggle="(v: boolean) => toggleGroup(g, v)"
              @probe="openProbe(g)"
              @edit="g.kind === 'static' ? openEdit(g) : openEditRuleGroup(g)"
              @remove="removeGroup(g)"
              @reset="resetGroup(g)"
            />
          </div>
        </ListPage>
      </el-tab-pane>

      <!-- ==================== 探测模板 ==================== -->
      <el-tab-pane name="templates">
        <template #label>
          <span class="tab-label">探测模板 <span class="tab-count">{{ templates.length }}</span></span>
        </template>

        <TemplatePanel
          :templates="templates"
          @reload="loadTemplates"
          @create="openTemplateCreate"
          @edit="openTemplateEdit"
          @remove="removeTemplate"
        />
      </el-tab-pane>

      <!-- ==================== 探测计划 ==================== -->
      <el-tab-pane name="plan">
        <template #label>
          <span class="tab-label">探测计划 <span class="tab-count">{{ plan.units.length }}</span></span>
        </template>

        <ProbePlanPanel
          :plan="plan"
          :form="globalProbeForm"
          :schedule="globalSchedule"
          :saving="savingProbe"
          @update:form="Object.assign(globalProbeForm, $event)"
          @update:schedule="Object.assign(globalSchedule, $event)"
          @reload="loadPlan"
          @save="saveGlobalProbe"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 探测设置弹窗（聚合） -->
    <BaseModal v-model:visible="probeVisible" :title="`探测设置：${probeName}`" size="large">
      <BaseNotice
        text="只影响本聚合的探测节奏与排序；探测对象是全局去重后的单元，多聚合共用同一模型时不会重复探测。" />
      <ProbeSettingsForm
        :form="probeForm"
        :templates="templates"
        :global-interval="globalInterval"
        @update:form="probeForm = $event"
      />
      <template #footer>
        <BaseModalFooter :loading="savingProbe" @cancel="probeVisible = false" @confirm="saveProbe" />
      </template>
    </BaseModal>

    <!-- 规则聚合候选（只读） -->
    <BaseModal v-model:visible="ruleVisible" :title="`规则聚合：${ruleName}`" size="large">
      <BaseNotice
        text="该聚合没有固定成员。请求进来时会按请求内容匹配路由规则，命中哪条就用哪条的候选；探测时覆盖全部规则候选的并集。" />
      <el-table :data="ruleUnits" size="small" stripe>
        <el-table-column prop="upstream_name" label="上游源" width="140" />
        <el-table-column prop="model" label="真实模型名" min-width="240" />
      </el-table>
      <BaseEmptyState v-if="!ruleUnits.length" compact description="当前路由规则没有任何候选" />
      <template #footer>
        <BaseButton variant="ghost" @click="ruleVisible = false">关闭</BaseButton>
      </template>
    </BaseModal>

    <!-- 模板编辑 -->
    <BaseModal v-model:visible="templateVisible"
      :title="templateEditId ? `编辑模板：${templateForm.name}` : '新建探测模板'" size="large">
      <el-form label-width="120px" style="margin-bottom: 8px">
        <el-form-item label="模板名" required>
          <BaseInput v-model="templateForm.name" placeholder="如：高频-交易时段" />
        </el-form-item>
        <el-form-item label="备注">
          <BaseInput v-model="templateForm.remark" placeholder="用途说明（可选）" />
        </el-form-item>
      </el-form>
      <ProbeSettingsForm
        :form="templateProbeForm"
        mode="template"
        :templates="[]"
        :global-interval="globalInterval"
        @update:form="templateProbeForm = $event"
      />
      <BaseHint v-if="templateRefNames.length" variant="warn" block>
        保存后将影响 {{ templateRefNames.length }} 个聚合：{{ templateRefNames.join('、') }}
      </BaseHint>
      <template #footer>
        <BaseModalFooter :loading="savingTemplate" @cancel="templateVisible = false" @confirm="saveTemplate" />
      </template>
    </BaseModal>

    <!-- 编辑/新建聚合 -->
    <AggregationEditModal
      v-model:visible="editVisible"
      :mode="editMode"
      :name="editName"
      :kind="editKind"
      :items="editItems"
      :catalog="ruleCatalog"
      :upstreams="upstreams"
      :source-models="sourceModels"
      :groups="editGroups"
      :group-options="groupOptions"
      :saving="savingEdit"
      @update:name="editName = $event"
      @update:kind="editKind = $event"
      @update:items="editItems = $event"
      @update:catalog="ruleCatalog = $event"
      @update:groups="editGroups = $event"
      @ensure-models="ensureSourceModels"
      @remove-item="removeItem"
      @save="saveEdit"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import ListPage from '@/components/list/ListPage.vue'
import ListToolbar from '@/components/list/ListToolbar.vue'
import FilterBar from '@/components/list/FilterBar.vue'
import FilterField from '@/components/list/FilterField.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import ChipFlow from '@/components/base/ChipFlow.vue'
import EntityCard from '@/components/base/EntityCard.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import { confirmAction, confirmDanger } from '@/components/base/BaseConfirm'
import ProbeSettingsForm, { type ProbeFormModel } from '@/components/probe/ProbeSettingsForm.vue'
import AggregationCard from '@/components/aggregation/AggregationCard.vue'
import AggregationEditModal from '@/components/aggregation/AggregationEditModal.vue'
import ProbePlanPanel from '@/components/aggregation/ProbePlanPanel.vue'
import TemplatePanel from '@/components/aggregation/TemplatePanel.vue'
import { buildCatalog, collectBindings, type BindItem, type MemberItem } from '@/components/aggregation/binding'
import { normalizeSchedule, validateSchedule } from '@/components/aggregation/schedule'
import { useTemplateEditor } from '@/composables/useTemplateEditor'
import {
  deleteAggregation,
  getProbePlan,
  listAggregations,
  listProbeTemplates,
  listRuleUnits,
  saveAggregation,
  type Aggregation,
  type ProbePlan,
  type ProbeSchedule,
  type ProbeTemplate,
} from '@/api/aggregations'
import { listGroupSuggestions, listSourceModels, saveModelGroup } from '@/api/model_groups'
import { getRules } from '@/api/rules'
import { listGroups } from '@/api/groups'
import { listUpstreams } from '@/api/upstreams'
import { getProbeConfig, saveProbeConfig } from '@/api/settings'
import { reloadConfig } from '@/api/common'

const routeTab = useRoute().query.tab
const activeTab = ref<'groups' | 'templates' | 'plan'>(
  routeTab === 'plan' ? 'plan' : routeTab === 'templates' ? 'templates' : 'groups',
)

// ---------- 聚合 ----------
const aggregations = ref<Aggregation[]>([])
const suggestions = ref<any[]>([])
const upstreams = ref<any[]>([])
const savingName = ref('')
/** 编辑弹窗独立保存态：不能复用 savingName（初值 '' 会让新建弹窗一开就卡「保存中」） */
const savingEdit = ref(false)
const merging = ref('')

// ---------- 聚合模型发现：分页 + 多选 + 批量合并（CH-045） ----------
const suggPage = ref(1)
const suggPageSize = ref(10)
const pagedSuggestions = computed(() => {
  const start = (suggPage.value - 1) * suggPageSize.value
  return suggestions.value.slice(start, start + suggPageSize.value)
})

/** 选中按归一化名存（suggestions 的唯一键），跨页保留 */
const selectedSuggestions = ref<string[]>([])

function toggleSuggChecked(key: string, checked: boolean) {
  if (checked) {
    if (!selectedSuggestions.value.includes(key)) selectedSuggestions.value.push(key)
  } else {
    selectedSuggestions.value = selectedSuggestions.value.filter((k) => k !== key)
  }
}

function clearSuggSelection() {
  selectedSuggestions.value = []
}

const suggPageKeys = computed(() => pagedSuggestions.value.map((s) => s.normalized))
const allSuggChecked = computed(() =>
  suggPageKeys.value.length > 0 && suggPageKeys.value.every((k) => selectedSuggestions.value.includes(k)),
)
const suggIndeterminate = computed(() => {
  const hit = suggPageKeys.value.filter((k) => selectedSuggestions.value.includes(k)).length
  return hit > 0 && hit < suggPageKeys.value.length
})

function toggleAllSuggestions(checked: boolean) {
  if (checked) {
    selectedSuggestions.value = [...new Set([...selectedSuggestions.value, ...suggPageKeys.value])]
  } else {
    const drop = new Set(suggPageKeys.value)
    selectedSuggestions.value = selectedSuggestions.value.filter((k) => !drop.has(k))
  }
}

/** 批量合并：逐条容错；全部走 mergeSuggestion 的同一套保存逻辑 */
async function batchMergeSuggestions() {
  const keys = [...selectedSuggestions.value]
  if (!keys.length) return
  if (!await confirmAction(`确定把选中的 ${keys.length} 个建议合并为聚合吗？`, '批量合并')) return

  const failed: string[] = []
  for (const key of keys) {
    const s = suggestions.value.find((x) => x.normalized === key)
    if (!s) continue
    try {
      const members = s.members.map((m: any) => ({ upstream: m.upstream, model: m.model, weight: 1 }))
      await saveModelGroup(s.suggested_name, members, true)
    } catch {
      failed.push(key)
    }
  }

  const done = keys.length - failed.length
  if (done > 0) ElMessage.success(`已合并 ${done} 个聚合`)
  if (failed.length) ElMessage.warning(`${failed.length} 个合并失败，已保留选中`)

  await reloadConfig()
  await loadAll()
  if ((suggPage.value - 1) * suggPageSize.value >= suggestions.value.length) suggPage.value = 1

  const alive = new Set(suggestions.value.map((s) => s.normalized))
  selectedSuggestions.value = failed.filter((k) => alive.has(k))
}

const suggBatchActions = computed(() => [
  { label: '批量合并', onClick: () => batchMergeSuggestions() },
])

// ---------- 聚合列表：分页 + 多选（CH-044） ----------
/** 筛选（CH-047：与 API Key 页对齐） */
const aggKeyword = ref('')
const aggKind = ref<'' | 'static' | 'rule'>('')
const aggEnabled = ref<'' | boolean>('')

const filteredAggs = computed(() => {
  const k = aggKeyword.value.trim().toLowerCase()
  return aggregations.value.filter((g) => {
    if (k && !String(g.name || '').toLowerCase().includes(k)) return false
    if (aggKind.value && g.kind !== aggKind.value) return false
    if (aggEnabled.value !== '' && Boolean(g.enabled) !== aggEnabled.value) return false
    return true
  })
})

function resetAggFilter() {
  aggKeyword.value = ''
  aggKind.value = ''
  aggEnabled.value = ''
  aggPage.value = 1
}

/** 列表级分页：分页归列表，不归卡片 */
const aggPage = ref(1)
const aggPageSize = ref(10)
const pagedAggs = computed(() => {
  const start = (aggPage.value - 1) * aggPageSize.value
  return filteredAggs.value.slice(start, start + aggPageSize.value)
})
const enabledAggCount = computed(() => aggregations.value.filter((g) => g.enabled).length)

/** 选中集合按聚合名存，跨页也保留（与 API Key 页的 row-key 做法一致） */
const selectedAggs = ref<string[]>([])

function toggleAggChecked(name: string, checked: boolean) {
  if (checked) {
    if (!selectedAggs.value.includes(name)) selectedAggs.value.push(name)
  } else {
    selectedAggs.value = selectedAggs.value.filter((n) => n !== name)
  }
}

function clearAggSelection() {
  selectedAggs.value = []
}

// ---------- 快捷全选（只作用于当前页，语义与表格表头全选一致） ----------
const pageNames = computed(() => pagedAggs.value.map((g) => g.name))
const allPageChecked = computed(() =>
  pageNames.value.length > 0 && pageNames.value.every((n) => selectedAggs.value.includes(n)),
)
const pageIndeterminate = computed(() => {
  const hit = pageNames.value.filter((n) => selectedAggs.value.includes(n)).length
  return hit > 0 && hit < pageNames.value.length
})

function toggleAllOnPage(checked: boolean) {
  if (checked) {
    // 只追加当前页，不动其它页已勾选的
    const merged = new Set([...selectedAggs.value, ...pageNames.value])
    selectedAggs.value = [...merged]
  } else {
    const drop = new Set(pageNames.value)
    selectedAggs.value = selectedAggs.value.filter((n) => !drop.has(n))
  }
}

/** 批量启用/禁用：操作后保留选中，避免用户重新勾一遍 */
async function batchToggleAgg(enabled: boolean) {
  const names = [...selectedAggs.value]
  if (!names.length) return
  const verb = enabled ? '启用' : '关闭'
  try {
    for (const name of names) {
      const g = aggregations.value.find((x) => x.name === name)
      if (!g) continue
      await saveAggregation(name, { kind: g.kind, enabled })
    }
    ElMessage.success(`已${verb} ${names.length} 个聚合`)
    await reloadConfig()
    await loadAll()
    // 重新拉取后可能超出现有页数，回到第一页兜底
    if ((aggPage.value - 1) * aggPageSize.value >= aggregations.value.length) aggPage.value = 1
    // 数据已换新对象，但选中是按名字存的，仍指向存在的项；清掉已消失的
    const alive = new Set(aggregations.value.map((g) => g.name))
    selectedAggs.value = names.filter((n) => alive.has(n))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || `批量${verb}失败`)
  }
}

/** 批量移除：逐条容错 + 与最新列表求交集，杜绝幽灵选中 */
async function batchRemoveAgg() {
  const names = [...selectedAggs.value]
  if (!names.length) return
  if (!await confirmDanger(`确定移除选中的 ${names.length} 个聚合吗？`, '移除后客户端将不能再使用这些聚合名。')) return

  const failed: string[] = []
  for (const name of names) {
    try {
      await deleteAggregation(name)
    } catch {
      failed.push(name)
    }
  }

  const removed = names.length - failed.length
  if (removed > 0) ElMessage.success(`已移除 ${removed} 个聚合`)
  if (failed.length) ElMessage.warning(`${failed.length} 个聚合移除失败，已保留选中`)

  await reloadConfig()
  await loadAll()
  if ((aggPage.value - 1) * aggPageSize.value >= aggregations.value.length) aggPage.value = 1

  const alive = new Set(aggregations.value.map((g) => g.name))
  selectedAggs.value = failed.filter((n) => alive.has(n))
}

const aggBatchActions = computed(() => [
  { label: '批量启用', onClick: () => batchToggleAgg(true) },
  { label: '批量关闭', onClick: () => batchToggleAgg(false) },
  { label: '批量移除', variant: 'danger' as const, onClick: () => batchRemoveAgg() },
])

// ---------- 模板 ----------
const templates = ref<ProbeTemplate[]>([])
const templateVisible = ref(false)
const templateEditId = ref<number | null>(null)
const savingTemplate = ref(false)
const templateRefNames = ref<string[]>([])
const templateForm = reactive({ name: '', remark: '' })
const templateProbeForm = ref<ProbeFormModel>(emptyProbeForm())

// ---------- 探测计划 ----------
const plan = ref<ProbePlan>({
  summary: { unit_count: 0, member_refs: 0, dedup_saved: 0, daily_requests: 0, global_interval: 120, aggregation_count: 0 },
  units: [],
})
const globalInterval = ref(120)
const globalProbeForm = reactive<any>({})
const globalSchedule = reactive<ProbeSchedule>({ mode: 'always', days: [], windows: [] })
const savingProbe = ref(false)

// ---------- 聚合探测弹窗 ----------
const probeVisible = ref(false)
const probeName = ref('')
const probeForm = ref<ProbeFormModel>(emptyProbeForm())

// ---------- 规则候选弹窗 ----------
const ruleVisible = ref(false)
const ruleName = ref('')
const ruleUnits = ref<any[]>([])

// ---------- 类型 + 规则绑定 ----------
const editKind = ref<'static' | 'rule'>('static')
const ruleCatalog = ref<BindItem[]>([])
const rules = ref<any[]>([])

// ---------- 成员编辑 ----------
const sourceModels = reactive<Record<string, string[]>>({})
const editVisible = ref(false)
const editMode = ref<'create' | 'edit'>('edit')
const editName = ref('')
const editItems = ref<MemberItem[]>([])
/** CH-034：聚合可用分组（空 = 所有 Key 可用） */
const editGroups = ref<string[]>([])
const groupOptions = ref<{ name: string; description?: string }[]>([])

const templateEditor = useTemplateEditor(templateForm, templateProbeForm, {
  emptyProbeForm,
  onSaved: loadAll,
})

function emptyProbeForm(): ProbeFormModel {
  return {
    enabled: false,
    template_id: null,
    interval_seconds: null,
    slow_threshold_seconds: null,
    sort_mode: 'stable',
    schedule: { mode: 'always', days: [], windows: [] },
  }
}

// ---------- 加载 ----------
async function loadAll() {
  const [aggs, sugg]: any = await Promise.all([listAggregations(), listGroupSuggestions()])
  aggregations.value = aggs.aggregations || []
  suggestions.value = sugg.suggestions || []
  await Promise.all([loadTemplates(), loadPlan(), loadGroups()])
}

/** CH-034：聚合可用分组下拉数据 */
async function loadGroups() {
  try {
    const res: any = await listGroups()
    groupOptions.value = (res.groups || []).map((g: any) => ({
      name: g.name, description: g.description || '',
    }))
  } catch {
    groupOptions.value = []
  }
}

async function loadTemplates() {
  const res: any = await listProbeTemplates()
  templates.value = res.templates || []
}

async function loadPlan() {
  const [pl, gc]: any = await Promise.all([getProbePlan(), getProbeConfig().catch(() => ({}))])
  plan.value = { summary: pl.summary || plan.value.summary, units: pl.units || [] }
  globalInterval.value = gc?.interval_seconds || 120
  Object.assign(globalProbeForm, gc || {})
  if (globalProbeForm.count_key_failures === undefined) globalProbeForm.count_key_failures = false
  if (globalProbeForm.max_concurrency === undefined) globalProbeForm.max_concurrency = 5
  const sched = gc?.schedule
  globalSchedule.mode = sched?.mode === 'window' ? 'window' : 'always'
  globalSchedule.days = [...(sched?.days || [])]
  globalSchedule.windows = (sched?.windows || []).map((w: any) => ({ start: w.start, end: w.end }))
}

async function loadUpstreams() {
  const res: any = await listUpstreams()
  upstreams.value = res.upstreams || []
}

async function loadRules() {
  try {
    const res: any = await getRules()
    rules.value = res.rules || []
  } catch {
    rules.value = []
  }
}

// ---------- 聚合操作 ----------
async function persistEnabled(g: Aggregation, enabled: boolean, successText: string) {
  savingName.value = g.name
  try {
    await saveAggregation(g.name, { kind: g.kind, enabled })
    ElMessage.success(successText)
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingName.value = ''
  }
}

function toggleGroup(g: Aggregation, enabled: boolean) {
  return persistEnabled(g, enabled, enabled ? `「${g.name}」已启用` : `「${g.name}」已关闭`)
}

async function resetGroup(g: Aggregation) {
  if (!await confirmAction(`确定对「${g.name}」恢复自动发现吗？手动配置将被删除。`, '恢复自动')) return
  savingName.value = g.name
  try {
    await deleteAggregation(g.name)
    ElMessage.success('已恢复自动发现')
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    savingName.value = ''
  }
}

async function removeGroup(g: Aggregation) {
  const message = g.kind === 'rule'
    ? `确定移除规则聚合「${g.name}」吗？移除后客户端不能再使用这个聚合名。`
    : `确定移除聚合「${g.name}」的配置吗？`
  if (!await confirmDanger(message, '移除聚合')) return
  savingName.value = g.name
  try {
    await deleteAggregation(g.name)
    ElMessage.success('已移除')
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    savingName.value = ''
  }
}

async function mergeSuggestion(s: any) {
  merging.value = s.normalized
  try {
    // 复用兼容端点（内部写统一表）
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

// ---------- 聚合探测设置 ----------
function openProbe(g: Aggregation) {
  probeName.value = g.name
  probeForm.value = {
    enabled: g.probe.enabled,
    template_id: g.template_id,
    interval_seconds: g.self_config.interval_seconds,
    slow_threshold_seconds: g.self_config.slow_threshold_seconds,
    sort_mode: g.self_config.sort_mode,
    schedule: {
      mode: g.self_config.schedule?.mode === 'window' ? 'window' : 'always',
      days: [...(g.self_config.schedule?.days || [])],
      windows: (g.self_config.schedule?.windows || []).map((w: any) => ({ start: w.start, end: w.end })),
    },
  }
  probeVisible.value = true
}

async function saveProbe() {
  const err = validateSchedule(probeForm.value.schedule)
  if (err) return ElMessage.warning(err)
  savingProbe.value = true
  try {
    await saveAggregation(probeName.value, {
      probe_enabled: probeForm.value.enabled,
      template_id: probeForm.value.template_id,
      interval_seconds: probeForm.value.interval_seconds,
      slow_threshold_seconds: probeForm.value.slow_threshold_seconds,
      sort_mode: probeForm.value.sort_mode,
      schedule: normalizeSchedule(probeForm.value.schedule),
    })
    ElMessage.success('探测设置已保存')
    probeVisible.value = false
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingProbe.value = false
  }
}

// ---------- 规则聚合候选（只读查看） ----------
async function openRuleDetail(g: Aggregation) {
  ruleName.value = g.name
  const res: any = await listRuleUnits(g.name)
  ruleUnits.value = res.units || []
  ruleVisible.value = true
}
// 模板列表面板目前不提供「查看绑定」入口，保留供后续使用
void openRuleDetail

// ---------- 模板 ----------
const openTemplateCreate = () => templateEditor.openCreate(() => {
  templateEditId.value = null
  templateRefNames.value = []
  templateVisible.value = true
})

const openTemplateEdit = (t: ProbeTemplate) => templateEditor.openEdit(t, () => {
  templateEditId.value = t.id
  templateRefNames.value = t.ref_names || []
  templateVisible.value = true
})

async function saveTemplate() {
  savingTemplate.value = true
  try {
    if (await templateEditor.save(templateEditId.value)) templateVisible.value = false
  } finally {
    savingTemplate.value = false
  }
}

async function removeTemplate(t: ProbeTemplate) {
  await templateEditor.remove(t)
}

// ---------- 全局探测默认值 ----------
async function saveGlobalProbe() {
  savingProbe.value = true
  try {
    await saveProbeConfig({ ...globalProbeForm, schedule: normalizeSchedule(globalSchedule) })
    ElMessage.success('全局探测设置已保存')
    await reloadConfig()
    await loadPlan()
  } finally {
    savingProbe.value = false
  }
}

// ---------- 成员编辑 ----------
async function ensureSourceModels(upstream: string) {
  if (!upstream || sourceModels[upstream]) return
  try {
    const res: any = await listSourceModels(upstream)
    sourceModels[upstream] = (res.models || []).map((m: any) => m.name)
  } catch {
    sourceModels[upstream] = []
  }
}

function openEdit(g: Aggregation) {
  editMode.value = 'edit'
  editName.value = g.name
  editKind.value = 'static'
  editGroups.value = [...(g.groups || [])]
  editItems.value = (g.members || []).map((m: any) => ({
    upstream: m.upstream,
    model: m.model || g.name,
    weight: m.weight || 1,
  }))
  editItems.value.forEach((it) => ensureSourceModels(it.upstream))
  editVisible.value = true
}

function openCreate() {
  editMode.value = 'create'
  editName.value = ''
  editKind.value = 'static'
  editGroups.value = []
  editItems.value = []
  ruleCatalog.value = buildCatalog(rules.value)
  ensureSourceModels(upstreams.value[0]?.id || '')
  editVisible.value = true
}

function removeItem(item: MemberItem) {
  editItems.value = editItems.value.filter(
    (x) => !(x.upstream === item.upstream && x.model === item.model),
  )
}

async function openEditRuleGroup(g: Aggregation) {
  editMode.value = 'edit'
  editName.value = g.name
  editKind.value = 'rule'
  editGroups.value = [...(g.groups || [])]
  ruleCatalog.value = buildCatalog(rules.value, g)
  editVisible.value = true
}

async function saveEdit() {
  const name = (editName.value || '').trim()
  if (!name) return ElMessage.warning('聚合名为必填')

  if (editKind.value === 'rule') {
    const used = ruleCatalog.value.filter((i) => i.used)
    if (!used.length) return ElMessage.warning('至少勾选一条规则')
    const empty = used.find((i) => !i.picked.length)
    if (empty) return ElMessage.warning(`规则「${empty.name}」至少要保留一个候选（或取消勾选该规则）`)
  } else if (!editItems.value.length) {
    return ElMessage.warning('至少添加一个成员')
  }

  savingEdit.value = true
  try {
    const payload: Record<string, unknown> = { kind: editKind.value, enabled: true, groups: editGroups.value }
    if (editKind.value === 'rule') {
      // rule 聚合不传 members（后端会拒绝）；规则绑定为空数组即"全跟随"
      payload.rule_bindings = collectBindings(ruleCatalog.value) || []
    } else {
      payload.members = editItems.value.map((x) => ({
        upstream: x.upstream, model: x.model, weight: x.weight,
      }))
      payload.rule_bindings = null
    }
    await saveAggregation(name, payload)
    ElMessage.success('聚合配置已保存')
    editVisible.value = false
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingEdit.value = false
  }
}

// ---------- 聚合列表排序（CH-044：移除前端拖拽） ----------
// 原 CH-028 的拖拽调序已去掉：
//   1. 它只决定纯展示顺序（架构设计 6.7 已写明不参与路由决策），去掉无功能损失；
//   2. 加分页后只能拖「当页」，容易让人误以为能全局排序，歧义大于收益；
//   3. 展示型列表的通用形态靠筛选/表头排序组织，不靠拖拽。
// 后端 PUT /admin/api/aggregations/order 保留不动（API 契约不受影响），
// 顺序仍由库里已有的 aggregation_order 决定。

onMounted(async () => {
  await Promise.all([loadUpstreams(), loadRules()])
  await loadAll()
})
</script>

<style scoped src="@/styles/aggregated.css"></style>
