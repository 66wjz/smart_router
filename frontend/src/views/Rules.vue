<template>
  <BaseSection variant="card" title="路由规则管理">
    <div class="toolbar">
      <BaseButton variant="primary" size="sm" @click="openAddRule">+ 新增规则</BaseButton>
    </div>

    <!-- 规则卡片列表 -->
    <div v-loading="loading">
      <BaseEmptyState v-if="!rules.length && !loading" description="暂无路由规则，请点击上方按钮新增" />
      <div v-for="(rule, i) in rules" :key="i" class="rule-card">
        <div class="rule-header">
          <div class="rule-title">
            <span class="rule-name">{{ rule.name }}</span>
            <BaseBadge variant="amber">{{ matchDesc(rule.match) }}</BaseBadge>
          </div>
          <div class="rule-actions">
            <BaseButton variant="ghost" size="sm" @click="openEditRule(rule, i)">修改</BaseButton>
            <BaseButton variant="danger" size="sm" @click="handleDeleteRule(i)">删除</BaseButton>
          </div>
        </div>
        <div v-for="(cands, prio) in groupByPriority(rule.candidates)" :key="prio" style="margin-top: 8px">
          <BaseBadge variant="blue" style="margin-bottom: 4px">优先级 {{ prio }}</BaseBadge>
          <el-table :data="cands" size="small" border style="margin-top: 4px">
            <el-table-column prop="model" label="模型" min-width="240" />
            <el-table-column prop="upstream" label="上游源" width="110" />
            <el-table-column prop="weight" label="权重" width="70" />
            <el-table-column label="最大上下文" width="110">
              <template #default="{ row }">{{ row.max_context || 'N/A' }}</template>
            </el-table-column>
            <el-table-column label="最大输出" width="100">
              <template #default="{ row }">{{ row.max_output || 'N/A' }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <!-- 规则编辑弹窗 -->
    <BaseModal v-model:visible="ruleModalVisible" :title="ruleEditIndex === null ? '新增规则' : `修改规则：${ruleForm.name || '(未命名)'}`" size="large" :height="'70vh'">
      <el-form :model="ruleForm" label-width="90px">
        <el-form-item label="规则名称" required>
          <BaseInput v-model="ruleForm.name" placeholder="例: 视觉理解、工具调用、默认对话" />
        </el-form-item>

        <!-- 匹配条件 -->
        <el-form-item label="匹配条件">
          <el-checkbox-group :model-value="matchedChecks" @update:model-value="onMatchCheck">
            <el-checkbox value="has_image">含图片</el-checkbox>
            <el-checkbox value="has_tools">含工具调用</el-checkbox>
            <el-checkbox value="default">默认（无条件）</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="内容关键词">
          <BaseInput v-model="ruleForm.match.content_keywords" placeholder="逗号分隔，命中任一关键词即匹配该规则（可选）" />
        </el-form-item>

        <!-- 候选模型 -->
        <el-form-item label="候选模型">
          <div style="width: 100%">
            <div v-for="(c, j) in ruleForm.candidates" :key="j" class="cand-item">
              <BaseBadge variant="default">{{ c.model }}</BaseBadge>
              <BaseBadge variant="gray">上游: {{ c.upstream }}</BaseBadge>
              <BaseBadge variant="amber">权重: {{ c.weight }}</BaseBadge>
              <BaseBadge variant="blue">P{{ c.priority }}</BaseBadge>
              <BaseBadge variant="green">ctx: {{ c.max_context || 'N/A' }}</BaseBadge>
              <BaseBadge variant="default">out: {{ c.max_output || 'N/A' }}</BaseBadge>
              <BaseButton variant="danger" size="sm" style="margin-left: auto" @click="ruleForm.candidates.splice(j, 1)">
                移除
              </BaseButton>
            </div>
            <BaseEmptyState v-if="!ruleForm.candidates.length" description="暂无候选模型，请在下方添加" />
          </div>
        </el-form-item>

        <!-- 添加候选 -->
        <el-form-item label="添加候选">
          <el-form inline label-width="70px" style="width: 100%">
            <el-form-item label="上游源">
              <el-select v-model="candForm.upstream" style="width: 140px" @change="onCandUpstreamChange">
                <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
              </el-select>
            </el-form-item>
            <el-form-item label="模型">
              <el-select
                v-if="(modelsByUpstream[candForm.upstream] || []).length"
                v-model="candForm.model"
                filterable
                style="width: 260px"
              >
                <el-option v-for="m in modelsByUpstream[candForm.upstream]" :key="m" :label="m" :value="m" />
              </el-select>
              <BaseInput v-else v-model="candForm.model" placeholder="模型名（手动输入）" style="width: 260px" />
            </el-form-item>
            <el-form-item label="权重">
              <el-input-number v-model="candForm.weight" :min="1" :max="10" />
            </el-form-item>
            <el-form-item label="优先级">
              <el-input-number v-model="candForm.priority" :min="1" :max="5" />
            </el-form-item>
            <el-form-item label="上下文">
              <el-input-number v-model="candForm.max_context" :min="0" :step="1000" />
            </el-form-item>
            <el-form-item label="输出">
              <el-input-number v-model="candForm.max_output" :min="0" :step="1000" />
            </el-form-item>
            <el-form-item>
              <BaseButton variant="primary" size="sm" @click="addCandidate">+ 添加到候选</BaseButton>
            </el-form-item>
          </el-form>
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="ruleModalVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="saving" @click="handleSaveRule">
          {{ saving ? '保存中...' : '保存规则' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- YAML 编辑（高级） -->
    <el-collapse style="margin-top: 16px">
      <el-collapse-item title="YAML 编辑（高级）" name="yaml">
        <BaseNotice title="直接编辑 JSON 格式的路由规则。修改后将整体保存并热重载。" />
        <BaseInput v-model="rulesYaml" type="textarea" :rows="14" placeholder="rules: [...]" />
        <div style="margin-top: 12px; display: flex; gap: 8px">
          <BaseButton variant="primary" :disabled="saving" @click="handleSaveYaml">
            {{ saving ? '保存中...' : '保存 YAML 规则' }}
          </BaseButton>
          <BaseButton variant="ghost" @click="initYaml">重新加载</BaseButton>
        </div>
      </el-collapse-item>
    </el-collapse>
  </BaseSection>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import { getRules, saveRules } from '@/api/rules'
import { listUpstreams } from '@/api/upstreams'
import { fetchUpstreamModels } from '@/api/aggregated'
import { reloadConfig } from '@/api/common'

const rules = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const upstreamIds = ref<string[]>([])
const modelsByUpstream = reactive<Record<string, string[]>>({})
const rulesYaml = ref('')

const ruleModalVisible = ref(false)
const ruleEditIndex = ref<number | null>(null)
const ruleForm = reactive<{
  name: string
  match: { has_image: boolean; has_tools: boolean; default: boolean; content_keywords: string }
  candidates: any[]
}>({ name: '', match: { has_image: false, has_tools: false, default: false, content_keywords: '' }, candidates: [] })

interface CandForm { upstream: string; model: string; weight: number; priority: number; max_context: number; max_output: number }
const candForm = reactive<CandForm>({ upstream: '', model: '', weight: 3, priority: 1, max_context: 1000000, max_output: 32768 })

const matchedChecks = computed<string[]>(() => {
  const m = ruleForm.match
  const checks: string[] = []
  if (m.has_image) checks.push('has_image')
  if (m.has_tools) checks.push('has_tools')
  if (m.default) checks.push('default')
  return checks
})

function onMatchCheck(val: string[]) {
  ruleForm.match.has_image = val.includes('has_image')
  ruleForm.match.has_tools = val.includes('has_tools')
  ruleForm.match.default = val.includes('default')
}

function matchDesc(match: any): string {
  const parts: string[] = []
  if (match?.has_image) parts.push('含图片')
  if (match?.has_tools) parts.push('含工具调用')
  if (match?.default) parts.push('默认')
  return parts.join(' + ') || '无条件'
}

function groupByPriority(cands: any[]) {
  const groups: Record<number, any[]> = {}
  cands.forEach((c) => {
    const p = c.priority || 1
    ;(groups[p] = groups[p] || []).push(c)
  })
  return groups
}

function resetCandForm() {
  candForm.upstream = upstreamIds.value[0] || ''
  candForm.model = ''
  candForm.weight = 3
  candForm.priority = 1
  candForm.max_context = 1000000
  candForm.max_output = 32768
}

async function load() {
  loading.value = true
  try {
    const [rulesRes, upsRes] = await Promise.all([getRules(), listUpstreams()])
    rules.value = (rulesRes as any).rules
    upstreamIds.value = (upsRes as any).upstreams.map((u: any) => u.id)
    initYaml()
    // 自动拉取各上游源模型列表
    upstreamIds.value.forEach((id) => {
      fetchUpstreamModels(id)
        .then((r: any) => (modelsByUpstream[id] = r.models || []))
        .catch(() => {})
    })
  } finally {
    loading.value = false
  }
}

function initYaml() {
  rulesYaml.value = JSON.stringify(rules.value, null, 2)
}

function openAddRule() {
  ruleEditIndex.value = null
  ruleForm.name = ''
  ruleForm.match = { has_image: false, has_tools: false, default: false, content_keywords: '' }
  ruleForm.candidates = []
  resetCandForm()
  ruleModalVisible.value = true
}

function openEditRule(rule: any, i: number) {
  ruleEditIndex.value = i
  const m = rule.match || {}
  ruleForm.name = rule.name
  ruleForm.match = {
    has_image: !!m.has_image,
    has_tools: !!m.has_tools,
    default: !!m.default,
    content_keywords: Array.isArray(m.content_keywords) ? m.content_keywords.join(', ') : (m.content_keywords || ''),
  }
  ruleForm.candidates = JSON.parse(JSON.stringify(rule.candidates || []))
  resetCandForm()
  ruleModalVisible.value = true
}

function onCandUpstreamChange() {
  candForm.model = ''
}

function addCandidate() {
  if (!candForm.model) {
    ElMessage.warning('请选择或输入模型名')
    return
  }
  ruleForm.candidates.push({ ...candForm })
  candForm.model = ''
}

function buildMatch(): Record<string, unknown> {
  const match: Record<string, unknown> = {}
  if (ruleForm.match.has_image) match.has_image = true
  if (ruleForm.match.has_tools) match.has_tools = true
  if (ruleForm.match.default) match.default = true
  const keywords = ruleForm.match.content_keywords
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean)
  if (keywords.length) match.content_keywords = keywords
  return match
}

async function saveAll() {
  await saveRules(rules.value)
  await reloadConfig()
  await load()
}

async function handleSaveRule() {
  if (!ruleForm.name) {
    ElMessage.warning('规则名称为必填')
    return
  }
  const rule = {
    name: ruleForm.name,
    match: buildMatch(),
    candidates: ruleForm.candidates.map((c) => ({
      model: c.model,
      upstream: c.upstream,
      weight: c.weight,
      priority: c.priority,
      max_context: c.max_context || null,
      max_output: c.max_output || null,
    })),
  }
  saving.value = true
  try {
    if (ruleEditIndex.value === null) {
      rules.value.push(rule)
    } else {
      rules.value[ruleEditIndex.value] = rule
    }
    await saveAll()
    ElMessage.success(ruleEditIndex.value === null ? '规则添加成功' : '规则修改成功')
    ruleModalVisible.value = false
  } finally {
    saving.value = false
  }
}

async function handleDeleteRule(i: number) {
  const rule = rules.value[i]
  if (!await confirmDanger(`确定删除规则「${rule.name}」吗？`)) return
  saving.value = true
  try {
    rules.value.splice(i, 1)
    await saveAll()
    ElMessage.success('规则已删除')
  } finally {
    saving.value = false
  }
}

async function handleSaveYaml() {
  saving.value = true
  try {
    const parsed = JSON.parse(rulesYaml.value)
    if (!Array.isArray(parsed)) {
      ElMessage.error('规则必须是列表格式')
      return
    }
    rules.value = parsed
    await saveAll()
    ElMessage.success('规则已保存')
  } catch (e: any) {
    ElMessage.error(`解析错误: ${e.message}`)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
.rule-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--bg-base);
}
.rule-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.rule-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rule-name {
  font-weight: 600;
  font-size: 1.05rem;
}
.cand-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  flex-wrap: wrap;
}
</style>
