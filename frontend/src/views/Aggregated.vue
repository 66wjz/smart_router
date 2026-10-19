<template>
  <div>
    <el-tabs v-model="activeTab" class="agg-tabs">
      <!-- ==================== 聚合组 ==================== -->
      <el-tab-pane name="groups">
        <template #label>
          <span class="tab-label">聚合组 <span class="tab-count">{{ aggregations.length }}</span></span>
        </template>

        <BaseSection v-if="suggestions.length" variant="card" title="疑似同一模型（建议合并）">
          <BaseNotice variant="warning"
            text="系统按「去前缀 + 忽略大小写 + 忽略 . _ 差异」识别出下列模型可能其实是同一个。确认后会合成一个聚合名，客户端用该名字即可自动跨源兜底。" />
          <div v-for="s in suggestions" :key="s.normalized" class="suggest-card">
            <div class="suggest-head">
              <div class="suggest-title">
                <BaseBadge variant="amber">建议聚合名</BaseBadge>
                <code class="group-model">{{ s.suggested_name }}</code>
                <BaseBadge variant="gray">{{ s.members.length }} 个成员</BaseBadge>
              </div>
              <BaseButton variant="primary" size="sm" :disabled="merging === s.normalized"
                @click="mergeSuggestion(s)">
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

        <BaseSection variant="card" title="聚合模型" style="margin-top: 16px">
          <template #actions>
            <BaseButton variant="ghost" size="sm" @click="loadAll">刷新</BaseButton>
            <BaseButton variant="primary" size="sm" @click="openCreate">+ 新建聚合</BaseButton>
          </template>

          <BaseNotice
            text="两类聚合统一管理：固定成员（可跨源、可异名）由你指定候选；规则聚合的候选由「路由规则」页在运行时按请求内容匹配，探测时会覆盖全部规则候选的并集。" />

          <BaseEmptyState v-if="!aggregations.length" compact
            description="当前没有聚合。同一模型名只存在于一个源时不构成聚合；异名模型可手动创建。" />

          <div v-else ref="aggListRef" class="agg-list">
            <AggregationCard
              v-for="g in aggregations"
              :key="g.name"
              :g="g"
              :saving="savingName === g.name"
              @toggle="(v: boolean) => toggleGroup(g, v)"
              @probe="openProbe(g)"
              @edit="g.kind === 'static' ? openEdit(g) : openEditRuleGroup(g)"
              @remove="removeGroup(g)"
              @reset="resetGroup(g)"
            />
          </div>
        </BaseSection>
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
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import Sortable from 'sortablejs'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
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
  reorderAggregations,
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

// ---------- 聚合列表拖拽排序（CH-028） ----------
const aggListRef = ref<HTMLElement | null>(null)
let aggSortable: Sortable | null = null

function initAggSortable() {
  if (!aggListRef.value) return
  aggSortable?.destroy()
  aggSortable = Sortable.create(aggListRef.value, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'drag-ghost',
    fallbackTolerance: 3,
    onEnd: async (evt) => {
      if ((evt.oldIndex ?? -1) === (evt.newIndex ?? -1)) return
      const domOrder = Array.from(aggListRef.value!.querySelectorAll('.group-card'))
        .map((n) => (n as HTMLElement).dataset.aggName || '')
        .filter(Boolean)
      const byName = new Map(aggregations.value.map((g) => [g.name, g]))
      const next = domOrder.map((n) => byName.get(n)).filter(Boolean) as Aggregation[]
      if (next.length !== aggregations.value.length) {
        // DOM 与数据长度不一致（异常情况）：直接回读后端顺序复原
        await loadAll()
        return
      }
      // 先同步本地数据，避免 Vue 用旧数组回写 DOM
      aggregations.value = next
      try {
        await reorderAggregations(next.map((g) => g.name))
        ElMessage.success('聚合顺序已保存')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.detail || '排序失败')
        await loadAll()
      }
    },
  })
}

watch(
  () => aggregations.value.length,
  () => nextTick(initAggSortable),
)

onMounted(async () => {
  await Promise.all([loadUpstreams(), loadRules()])
  await loadAll()
  await nextTick()
  initAggSortable()
})

onBeforeUnmount(() => {
  aggSortable?.destroy()
  aggSortable = null
})
</script>

<style scoped src="@/styles/aggregated.css"></style>
