<template>
  <div>
    <el-tabs v-model="activeTab" class="agg-tabs">
      <!-- ==================== 聚合组 ==================== -->
      <el-tab-pane name="groups">
        <template #label>
          <span class="tab-label">聚合组 <span class="tab-count">{{ aggregations.length }}</span></span>
        </template>

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

        <BaseSection variant="card" title="聚合模型" style="margin-top: 16px">
          <template #actions>
            <BaseButton variant="ghost" size="sm" @click="loadAll">刷新</BaseButton>
            <BaseButton variant="primary" size="sm" @click="openCreate">+ 新建聚合</BaseButton>
          </template>

          <el-alert
            title="两类聚合统一管理：固定成员（可跨源、可异名）由你指定候选；规则聚合的候选由「路由规则」页在运行时按请求内容匹配，探测时会覆盖全部规则候选的并集。"
            type="info"
            :closable="false"
            style="margin-bottom: 16px"
          />

          <div v-if="!aggregations.length" class="empty-tip">
            <el-text type="info">当前没有聚合。同一模型名只存在于一个源时不构成聚合；异名模型可手动创建。</el-text>
          </div>

          <div v-for="g in aggregations" :key="g.name" class="group-card">
            <div class="group-head">
              <div class="group-title">
                <code class="group-model">{{ g.name }}</code>
                <BaseBadge :variant="g.kind === 'rule' ? 'purple' : 'blue'">
                  {{ g.kind === 'rule' ? '规则匹配' : '固定成员' }}
                </BaseBadge>
                <BaseBadge v-if="!g.configured" variant="gray">自动发现</BaseBadge>
                <BaseBadge v-if="g.template_name" variant="green">模板: {{ g.template_name }}</BaseBadge>
                <BaseBadge :variant="g.probe.sort_mode === 'latency' ? 'amber' : 'gray'">
                  {{ g.probe.sort_mode === 'latency' ? '速度优先' : '稳定优先' }}
                </BaseBadge>
                <BaseBadge :variant="probeBadge(g).variant">{{ probeBadge(g).text }}</BaseBadge>
                <BaseBadge v-if="!g.enabled" variant="red">聚合已关闭</BaseBadge>
              </div>
              <div class="group-ops">
                <span class="op-label">启用</span>
                <el-switch
                  :model-value="g.enabled"
                  size="small"
                  :disabled="savingName === g.name"
                  @change="(val: boolean | string | number) => toggleGroup(g, Boolean(val))"
                />
                <BaseButton variant="ghost" size="sm" @click="openProbe(g)">探测设置</BaseButton>
                <BaseButton v-if="g.kind === 'static'" variant="primary" size="sm"
                  :disabled="savingName === g.name" @click="openEdit(g)">
                  {{ savingName === g.name ? '保存中…' : '编辑成员' }}
                </BaseButton>
                <BaseButton v-else variant="ghost" size="sm" @click="openRuleDetail(g)">查看候选</BaseButton>
                <BaseButton v-if="g.kind === 'rule' || !g.configured" variant="danger" size="sm"
                  :disabled="savingName === g.name" @click="removeGroup(g)">移除</BaseButton>
                <BaseButton v-else variant="ghost" size="sm"
                  :disabled="savingName === g.name" @click="resetGroup(g)">恢复自动</BaseButton>
              </div>
            </div>

            <!-- 固定成员：候选链路 -->
            <div v-if="g.kind === 'static'" class="source-flow">
              <template v-for="(m, i) in g.members" :key="m.upstream + (m.model || '')">
                <span class="source-chip" :class="{ 'is-first': i === 0 }">
                  <span class="chip-index">{{ i + 1 }}</span>
                  <span class="chip-src">{{ m.upstream }}</span>
                  <code class="chip-model">{{ m.model || g.name }}</code>
                  <el-text v-if="i === 0" type="success" size="small">首选</el-text>
                  <el-text v-else-if="i === g.members.length - 1" type="info" size="small">兜底</el-text>
                </span>
                <span v-if="i < g.members.length - 1" class="arrow">→</span>
              </template>
              <span v-if="!g.members.length" class="empty-tip"><el-text type="warning">没有任何可用成员</el-text></span>
            </div>

            <!-- 规则聚合：匹配的规则名 -->
            <div v-else class="rule-flow">
              <span class="rule-hint">候选由路由规则决定，运行时按请求内容匹配：</span>
              <BaseBadge v-for="r in g.rule_names || []" :key="r" variant="purple">{{ r }}</BaseBadge>
              <span class="rule-cost">覆盖 {{ g.member_count }} 个探测单元</span>
            </div>

            <div v-if="!g.enabled" class="group-warn">
              <el-text type="warning" size="small">
                {{ g.kind === 'rule' ? '聚合已关闭：客户端请求该名字将不再走规则路由。' : '聚合已关闭：请求该名字时只走第一个可用成员，不做跨源兜底。' }}
              </el-text>
            </div>
          </div>
        </BaseSection>
      </el-tab-pane>

      <!-- ==================== 探测模板 ==================== -->
      <el-tab-pane name="templates">
        <template #label>
          <span class="tab-label">探测模板 <span class="tab-count">{{ templates.length }}</span></span>
        </template>

        <BaseSection variant="card" title="探测模板">
          <template #actions>
            <BaseButton variant="ghost" size="sm" @click="loadTemplates">刷新</BaseButton>
            <BaseButton variant="primary" size="sm" @click="openTemplateCreate">+ 新建模板</BaseButton>
          </template>

          <el-alert
            title="模板 = 一套可复用的探测节奏（间隔 / 慢阈值 / 排序 / 时段）。多个聚合挂同一模板后共用同一节奏，改模板即全部生效；挂模板的聚合不再使用自己的探测参数。"
            type="info"
            :closable="false"
            style="margin-bottom: 16px"
          />

          <div v-if="!templates.length" class="empty-tip">
            <el-text type="info">还没有探测模板。可以先建一个「标准-全天」模板，再挂到常用聚合上。</el-text>
          </div>

          <el-table v-else :data="templates" size="small" stripe>
            <el-table-column label="模板名" min-width="160">
              <template #default="{ row }">
                <span class="tpl-name">{{ row.name }}</span>
                <el-text v-if="row.remark" type="info" size="small" style="margin-left: 8px">{{ row.remark }}</el-text>
              </template>
            </el-table-column>
            <el-table-column label="间隔" width="90">
              <template #default="{ row }">{{ row.interval_seconds }}s</template>
            </el-table-column>
            <el-table-column label="慢阈值" width="90">
              <template #default="{ row }">
                {{ row.slow_threshold_seconds != null ? `${row.slow_threshold_seconds}s` : '跟随全局' }}
              </template>
            </el-table-column>
            <el-table-column label="排序" width="100">
              <template #default="{ row }">
                <BaseBadge :variant="row.sort_mode === 'latency' ? 'amber' : 'gray'">
                  {{ row.sort_mode === 'latency' ? '速度优先' : '稳定优先' }}
                </BaseBadge>
              </template>
            </el-table-column>
            <el-table-column label="探测时段" min-width="180">
              <template #default="{ row }">{{ describeSchedule(row.schedule) }}</template>
            </el-table-column>
            <el-table-column label="被引用" min-width="200">
              <template #default="{ row }">
                <BaseBadge v-for="n in row.ref_names || []" :key="n" variant="blue" style="margin-right: 4px">{{ n }}</BaseBadge>
                <el-text v-if="!row.ref_count" type="info" size="small">暂无聚合使用</el-text>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <BaseButton variant="ghost" size="sm" @click="openTemplateEdit(row)">编辑</BaseButton>
                <BaseButton variant="danger" size="sm" style="margin-left: 6px" @click="removeTemplate(row)">删除</BaseButton>
              </template>
            </el-table-column>
          </el-table>
        </BaseSection>
      </el-tab-pane>

      <!-- ==================== 探测计划 ==================== -->
      <el-tab-pane name="plan">
        <template #label>
          <span class="tab-label">探测计划 <span class="tab-count">{{ plan.units.length }}</span></span>
        </template>

        <BaseSection variant="card" title="探测排班表">
          <template #actions>
            <BaseButton variant="ghost" size="sm" @click="loadPlan">刷新</BaseButton>
          </template>
          <ProbeScheduleTable :plan="plan" />
        </BaseSection>

        <BaseSection variant="card" title="全局探测默认值" style="margin-top: 16px">
          <el-alert
            title="未挂模板、也未自配的聚合会继承这里的值。这里仅控制「怎么探」，不控制「探哪些」。"
            type="info"
            :closable="false"
            style="margin-bottom: 16px"
          />
          <el-form label-width="150px" style="max-width: 760px">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="启用延迟探测">
                  <el-switch v-model="globalProbeForm.enabled" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="探测间隔（秒）">
                  <el-input-number v-model="globalProbeForm.interval_seconds" :min="10" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="慢阈值（秒）">
                  <el-input-number v-model="globalProbeForm.slow_threshold_seconds" :min="1" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="探测并发数">
                  <el-input-number v-model="globalProbeForm.max_concurrency" :min="1" :max="50" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="不可用阈值（秒）">
                  <el-input-number v-model="globalProbeForm.down_threshold_seconds" :min="5" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="基准延迟（秒）">
                  <el-input-number v-model="globalProbeForm.base_latency" :min="0.1" :step="0.1" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="探测超时（秒）">
                  <el-input-number v-model="globalProbeForm.timeout_seconds" :min="5" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="探测失败计入 Key 冷却">
                  <el-switch v-model="globalProbeForm.count_key_failures" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="全局探测时段">
              <el-radio-group v-model="globalSchedule.mode">
                <el-radio value="always">全天候</el-radio>
                <el-radio value="window">仅指定时段</el-radio>
              </el-radio-group>
            </el-form-item>
            <template v-if="globalSchedule.mode === 'window'">
              <el-form-item label="星期">
                <el-checkbox-group v-model="globalSchedule.days">
                  <el-checkbox v-for="d in DAY_OPTIONS" :key="d.value" :value="d.value">{{ d.label }}</el-checkbox>
                </el-checkbox-group>
                <div class="hint">不勾选 = 每天。仅作用于没有聚合/模板指定的单元。</div>
              </el-form-item>
              <el-form-item label="时段窗口">
                <div class="window-list">
                  <div v-for="(w, i) in globalSchedule.windows" :key="i" class="window-row">
                    <el-time-select v-model="w.start" start="00:00" end="23:30" step="00:30" placeholder="开始" style="width: 130px" />
                    <span class="sep">→</span>
                    <el-time-select v-model="w.end" start="00:30" end="23:59" step="00:30" placeholder="结束" style="width: 130px" />
                    <BaseButton variant="danger" size="sm" @click="globalSchedule.windows.splice(i, 1)">删除</BaseButton>
                  </div>
                  <BaseButton variant="ghost" size="sm" @click="globalSchedule.windows.push({ start: '08:00', end: '23:00' })">
                    + 添加时段
                  </BaseButton>
                </div>
              </el-form-item>
            </template>
            <el-form-item>
              <BaseButton variant="primary" :disabled="savingProbe" @click="saveGlobalProbe">
                {{ savingProbe ? '保存中...' : '保存全局探测设置' }}
              </BaseButton>
            </el-form-item>
          </el-form>
        </BaseSection>

        <BaseSection variant="card" title="探测单元明细" style="margin-top: 16px">
          <el-table :data="plan.units" size="small" stripe>
            <el-table-column prop="upstream_name" label="上游源" width="130" />
            <el-table-column prop="model" label="真实模型名" min-width="200" show-overflow-tooltip />
            <el-table-column label="引用聚合" min-width="200">
              <template #default="{ row }">
                <BaseBadge v-for="g in row.groups" :key="g"
                  :variant="row.group_kinds[g] === 'rule' ? 'purple' : 'blue'" style="margin-right: 4px">
                  {{ g }}
                </BaseBadge>
                <el-text v-if="!row.groups.length" type="info" size="small">仅规则/别名</el-text>
              </template>
            </el-table-column>
            <el-table-column label="间隔" width="80">
              <template #default="{ row }">{{ row.interval }}s</template>
            </el-table-column>
            <el-table-column label="最近延迟" width="90">
              <template #default="{ row }">{{ row.latency != null ? `${row.latency}s` : 'N/A' }}</template>
            </el-table-column>
            <el-table-column label="最近探测" width="160">
              <template #default="{ row }">{{ fmtTime(row.last_check) }}</template>
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
      </el-tab-pane>
    </el-tabs>

    <!-- 探测设置弹窗（聚合） -->
    <BaseModal v-model:visible="probeVisible" :title="`探测设置：${probeName}`" size="large">
      <el-alert
        title="只影响本聚合的探测节奏与排序；探测对象是全局去重后的单元，多聚合共用同一模型时不会重复探测。"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <ProbeSettingsForm
        :form="probeForm"
        :templates="templates"
        :global-interval="globalInterval"
        @update:form="probeForm = $event"
      />
      <template #footer>
        <BaseButton variant="ghost" @click="probeVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="savingProbe" @click="saveProbe">
          {{ savingProbe ? '保存中…' : '保存' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 规则聚合候选 -->
    <BaseModal v-model:visible="ruleVisible" :title="`规则聚合：${ruleName}`" size="large">
      <el-alert
        title="该聚合没有固定成员。请求进来时会按请求内容匹配路由规则，命中哪条就用哪条的候选；探测时覆盖全部规则候选的并集。"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-table :data="ruleUnits" size="small" stripe>
        <el-table-column prop="upstream_name" label="上游源" width="140" />
        <el-table-column prop="model" label="真实模型名" min-width="240" />
      </el-table>
      <el-text v-if="!ruleUnits.length" type="info">当前路由规则没有任何候选</el-text>
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
      <el-text v-if="templateRefNames.length" type="warning" size="small">
        保存后将影响 {{ templateRefNames.length }} 个聚合：{{ templateRefNames.join('、') }}
      </el-text>
      <template #footer>
        <BaseButton variant="ghost" @click="templateVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="savingTemplate" @click="saveTemplate">
          {{ savingTemplate ? '保存中…' : '保存' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 编辑/新建固定成员聚合 -->
    <BaseModal v-model:visible="editVisible" :title="editMode === 'create' ? '新建聚合' : `编辑聚合：${editName}`" size="large">
      <el-alert
        title="拖动调整优先级（从上到下即请求尝试顺序）；每个成员可指定该源里的真实模型名，因此不同源的异名模型也能聚合到一起。"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-form label-width="90px" style="margin-bottom: 12px">
        <el-form-item label="聚合名" required>
          <BaseInput v-model="editName" :disabled="editMode === 'edit'" placeholder="客户端请求时使用的名字，如 deepseek-v4-1-flash" />
        </el-form-item>
      </el-form>

      <div ref="dragListRef" class="drag-list">
        <div v-for="item in editItems" :key="item.upstream + '|' + item.model" class="drag-item">
          <span class="drag-handle" role="button" tabindex="0" aria-label="拖动调整顺序" title="拖动调整顺序">⠿</span>
          <span class="drag-upstream">{{ item.upstream }}</span>
          <el-select v-model="item.model" filterable allow-create default-first-option size="small"
            class="drag-model-select" placeholder="该源里的真实模型名">
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
        <el-select v-model="addModel" filterable allow-create default-first-option size="small"
          placeholder="选择/输入真实模型名" style="width: 300px">
          <el-option v-for="m in modelsOf(addUpstream)" :key="m" :label="m" :value="m" />
        </el-select>
        <BaseButton variant="primary" size="sm" @click="addItem">+ 添加成员</BaseButton>
      </div>

      <template #footer>
        <BaseButton variant="ghost" @click="editVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="savingName === editName" @click="saveEdit">
          {{ savingName === editName ? '保存中…' : '保存' }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import ProbeSettingsForm, { type ProbeFormModel } from '@/components/probe/ProbeSettingsForm.vue'
import ProbeScheduleTable from '@/components/probe/ProbeScheduleTable.vue'
import {
  createProbeTemplate,
  deleteAggregation,
  deleteProbeTemplate,
  getProbePlan,
  listAggregations,
  listProbeTemplates,
  listRuleUnits,
  saveAggregation,
  updateProbeTemplate,
  type Aggregation,
  type ProbePlan,
  type ProbeSchedule,
  type ProbeTemplate,
} from '@/api/aggregations'
import { listGroupSuggestions, listSourceModels, saveModelGroup } from '@/api/model_groups'
import { listUpstreams } from '@/api/upstreams'
import { getProbeConfig, saveProbeConfig } from '@/api/settings'
import { reloadConfig } from '@/api/common'

type BadgeVariant = 'default' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'gray'

const activeTab = ref<'groups' | 'templates' | 'plan'>(
  (useRoute().query.tab as any) === 'plan' ? 'plan'
    : (useRoute().query.tab as any) === 'templates' ? 'templates' : 'groups',
)

// ---------- 聚合 ----------
const aggregations = ref<Aggregation[]>([])
const suggestions = ref<any[]>([])
const upstreams = ref<any[]>([])
const savingName = ref('')
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

// ---------- 成员编辑 ----------
const sourceModels = reactive<Record<string, string[]>>({})
const editVisible = ref(false)
const editMode = ref<'create' | 'edit'>('edit')
const editName = ref('')
const editItems = ref<{ upstream: string; model: string; weight: number }[]>([])
const dragListRef = ref<HTMLElement | null>(null)
let sortable: Sortable | null = null
const addUpstream = ref('')
const addModel = ref('')

const DAY_OPTIONS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
]

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

function probeBadge(g: Aggregation): { text: string; variant: BadgeVariant } {
  if (!g.probe.enabled) return { text: '探测: 关', variant: 'gray' }
  const sched = g.probe.schedule?.mode === 'window' ? ' · 限时段' : ''
  const src = g.template_name ? `模板` : g.self_config.interval_seconds ? '' : '全局'
  return { text: `探测: 开 · ${src}${g.probe.interval_seconds}s${sched}`, variant: 'green' }
}

function describeSchedule(raw: ProbeSchedule | undefined): string {
  if (!raw || raw.mode !== 'window') return '全天候'
  const names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  const days = raw.days || []
  const dayText = !days.length || days.length === 7
    ? '每天'
    : days.length === 5 && days.every((d) => d <= 5) ? '工作日'
      : days.length === 2 && days.includes(6) && days.includes(7) ? '周末'
        : days.map((d) => names[d - 1]).join('、')
  const windows = raw.windows || []
  if (!windows.length) return `${dayText} 全天`
  return `${dayText} ${windows.map((w) => `${w.start}-${w.end}`).join('、')}`
}

function fmtTime(ts: number): string {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

// ---------- 加载 ----------
async function loadAll() {
  const [aggs, sugg]: any = await Promise.all([listAggregations(), listGroupSuggestions()])
  aggregations.value = aggs.aggregations || []
  suggestions.value = sugg.suggestions || []
  await Promise.all([loadTemplates(), loadPlan()])
}

async function loadTemplates() {
  const res: any = await listProbeTemplates()
  templates.value = res.templates || []
}

async function loadPlan() {
  const [pl, gc]: any = await Promise.all([getProbePlan(), getProbeConfig().catch(() => ({}))])
  plan.value = {
    summary: pl.summary || plan.value.summary,
    units: pl.units || [],
  }
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

// ---------- 聚合操作 ----------
async function toggleGroup(g: Aggregation, enabled: boolean) {
  savingName.value = g.name
  try {
    await saveAggregation(g.name, { kind: g.kind, enabled })
    ElMessage.success(enabled ? `「${g.name}」已启用` : `「${g.name}」已关闭`)
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingName.value = ''
  }
}

async function resetGroup(g: Aggregation) {
  await ElMessageBox.confirm(`确定对「${g.name}」恢复自动发现吗？手动配置将被删除。`, '恢复自动', { type: 'warning' })
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
  await ElMessageBox.confirm(
    g.kind === 'rule'
      ? `确定移除规则聚合「${g.name}」吗？移除后客户端不能再使用这个聚合名。`
      : `确定移除聚合「${g.name}」的配置吗？`,
    '移除聚合',
    { type: 'warning' },
  )
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
  const sched = probeForm.value.schedule
  if (sched.mode === 'window') {
    for (const w of sched.windows) {
      if (!w.start || !w.end) return ElMessage.warning('时段窗口需要同时填写开始和结束')
      if (w.start === w.end) return ElMessage.warning('时段的开始与结束不能相同')
    }
  }
  savingProbe.value = true
  try {
    await saveAggregation(probeName.value, {
      probe_enabled: probeForm.value.enabled,
      template_id: probeForm.value.template_id,
      interval_seconds: probeForm.value.interval_seconds,
      slow_threshold_seconds: probeForm.value.slow_threshold_seconds,
      sort_mode: probeForm.value.sort_mode,
      schedule: {
        mode: sched.mode,
        days: sched.mode === 'window' ? sched.days : [],
        windows: sched.mode === 'window' ? sched.windows : [],
      },
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

// ---------- 规则聚合候选 ----------
async function openRuleDetail(g: Aggregation) {
  ruleName.value = g.name
  const res: any = await listRuleUnits()
  ruleUnits.value = res.units || []
  ruleVisible.value = true
}

// ---------- 模板 ----------
function openTemplateCreate() {
  templateEditId.value = null
  templateForm.name = ''
  templateForm.remark = ''
  templateRefNames.value = []
  templateProbeForm.value = { ...emptyProbeForm(), enabled: true, interval_seconds: 300, sort_mode: 'stable' }
  templateVisible.value = true
}

function openTemplateEdit(t: ProbeTemplate) {
  templateEditId.value = t.id
  templateForm.name = t.name
  templateForm.remark = t.remark || ''
  templateRefNames.value = t.ref_names || []
  templateProbeForm.value = {
    enabled: true,
    template_id: null,
    interval_seconds: t.interval_seconds,
    slow_threshold_seconds: t.slow_threshold_seconds,
    sort_mode: t.sort_mode,
    schedule: {
      mode: t.schedule?.mode === 'window' ? 'window' : 'always',
      days: [...(t.schedule?.days || [])],
      windows: (t.schedule?.windows || []).map((w: any) => ({ start: w.start, end: w.end })),
    },
  }
  templateVisible.value = true
}

async function saveTemplate() {
  const name = templateForm.name.trim()
  if (!name) return ElMessage.warning('模板名不能为空')
  const interval = Number(templateProbeForm.value.interval_seconds) || 0
  if (interval < 10) return ElMessage.warning('探测间隔不能小于 10 秒')
  const sched = templateProbeForm.value.schedule
  if (sched.mode === 'window') {
    for (const w of sched.windows) {
      if (!w.start || !w.end) return ElMessage.warning('时段窗口需要同时填写开始和结束')
      if (w.start === w.end) return ElMessage.warning('时段的开始与结束不能相同')
    }
  }
  savingTemplate.value = true
  try {
    const payload = {
      name,
      interval_seconds: interval,
      slow_threshold_seconds: templateProbeForm.value.slow_threshold_seconds,
      sort_mode: templateProbeForm.value.sort_mode,
      schedule: {
        mode: sched.mode,
        days: sched.mode === 'window' ? sched.days : [],
        windows: sched.mode === 'window' ? sched.windows : [],
      },
      remark: templateForm.remark,
    }
    if (templateEditId.value) {
      await updateProbeTemplate(templateEditId.value, payload as any)
    } else {
      await createProbeTemplate(payload as any)
    }
    ElMessage.success('模板已保存')
    templateVisible.value = false
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingTemplate.value = false
  }
}

async function removeTemplate(t: ProbeTemplate) {
  const refs = t.ref_names || []
  const tip = refs.length
    ? `模板「${t.name}」正被 ${refs.length} 个聚合使用（${refs.join('、')}）。删除后这些聚合将回退到自配参数。确认删除？`
    : `确定删除模板「${t.name}」吗？`
  await ElMessageBox.confirm(tip, '删除模板', { type: 'warning' })
  try {
    await deleteProbeTemplate(t.id)
    ElMessage.success('模板已删除')
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

// ---------- 全局探测默认值 ----------
async function saveGlobalProbe() {
  savingProbe.value = true
  try {
    await saveProbeConfig({
      ...globalProbeForm,
      schedule: {
        mode: globalSchedule.mode,
        days: globalSchedule.mode === 'window' ? globalSchedule.days : [],
        windows: globalSchedule.mode === 'window' ? globalSchedule.windows : [],
      },
    })
    ElMessage.success('全局探测设置已保存')
    await reloadConfig()
    await loadPlan()
  } finally {
    savingProbe.value = false
  }
}

// ---------- 成员编辑 ----------
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

function openEdit(g: Aggregation) {
  editMode.value = 'edit'
  editName.value = g.name
  editItems.value = (g.members || []).map((m: any) => ({
    upstream: m.upstream,
    model: m.model || g.name,
    weight: m.weight || 1,
  }))
  editItems.value.forEach((it) => ensureSourceModels(it.upstream))
  editVisible.value = true
  nextTick(initSortable)
}

function openCreate() {
  editMode.value = 'create'
  editName.value = ''
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
  const name = (editName.value || '').trim()
  if (!name) return ElMessage.warning('聚合名为必填')
  if (!editItems.value.length) return ElMessage.warning('至少添加一个成员')
  savingName.value = name
  try {
    await saveAggregation(name, {
      kind: 'static',
      members: editItems.value.map((x) => ({ upstream: x.upstream, model: x.model, weight: x.weight })),
      enabled: true,
    })
    ElMessage.success('聚合配置已保存')
    editVisible.value = false
    await reloadConfig()
    await loadAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingName.value = ''
  }
}

onMounted(async () => {
  await loadUpstreams()
  await loadAll()
})
</script>

<style scoped>
.agg-tabs :deep(.el-tabs__content) {
  padding-top: 8px;
}
.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.tab-count {
  display: inline-block;
  min-width: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--bg-hover);
  color: var(--text-tertiary);
  font-size: 0.7rem;
  line-height: 18px;
  text-align: center;
}

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

/* 聚合卡片 */
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
  flex-wrap: wrap;
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
.rule-flow {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
  font-size: 0.8rem;
}
.rule-hint {
  color: var(--text-tertiary);
}
.rule-cost {
  color: var(--text-tertiary);
  font-size: 0.75rem;
}
.group-warn {
  margin-top: 8px;
}

/* 模板表 */
.tpl-name {
  font-weight: 600;
}
.tpl-remark {
  color: var(--text-tertiary);
}

/* 成员编辑 */
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
