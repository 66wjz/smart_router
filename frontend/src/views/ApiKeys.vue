<template>
  <BaseSection
    variant="card"
    title="路由层 API Key 管理"
    description="这些 Key 是客户端访问 Smart Router 的入场券。校验通过后，路由器会用各 upstream 自己的 Key 去访问模型提供商。"
  >
    <div class="toolbar">
      <BaseButton variant="primary" size="sm" @click="openAdd">+ 新增 Key</BaseButton>
    </div>

    <!-- Key 列表 -->
    <el-table :data="keys" stripe v-loading="loading">
      <el-table-column label="名称" min-width="140">
        <template #default="{ row }">{{ row.name }}</template>
      </el-table-column>
      <el-table-column label="Key" min-width="200">
        <template #default="{ row }">
          <el-text type="info" size="small">{{ row.key_masked }}</el-text>
        </template>
      </el-table-column>
      <el-table-column label="分组" width="200">
        <template #default="{ row }">
          <BaseBadge v-for="g in row.groups" :key="g" variant="default" style="margin-right: 4px">{{ g }}</BaseBadge>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <BaseBadge :variant="row.enabled ? 'green' : 'red'">
            {{ row.enabled ? '启用' : '禁用' }}
          </BaseBadge>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="420" fixed="right">
        <template #default="{ row }">
          <div class="row-actions">
            <BaseButton variant="ghost" size="sm" @click="openEdit(row)">修改</BaseButton>
            <BaseButton variant="ghost" size="sm" @click="handleToggle(row)">
              {{ row.enabled ? '禁用' : '启用' }}
            </BaseButton>
            <BaseButton variant="primary" size="sm" @click="showCopy(row)">复制 Key</BaseButton>
            <BaseButton variant="ghost" size="sm" @click="openUsage(row)">接入说明</BaseButton>
            <BaseButton variant="danger" size="sm" @click="handleDelete(row)">删除</BaseButton>
          </div>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无 API Key，请点击上方按钮新增" />
      </template>
    </el-table>

    <!-- 新增 Key 弹窗 -->
    <BaseModal v-model:visible="addVisible" title="新增 API Key" size="wide">
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="名称">
          <BaseInput v-model="addForm.name" placeholder="例: 扣子平台、开发测试" />
        </el-form-item>
        <el-form-item label="Key 值" required>
          <div class="key-input-row">
            <BaseInput v-model="addForm.key" type="password" placeholder="sk-my-key-123" show-password />
            <BaseButton variant="ghost" size="sm" @click="regenerate">重新生成</BaseButton>
          </div>
          <el-text type="info" size="small">已自动生成随机 Key，也可手动修改或点击「重新生成」换一个</el-text>
        </el-form-item>
        <el-form-item label="分组">
          <el-select v-model="addForm.groups" multiple placeholder="选择分组" style="width: 100%">
            <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
          <el-text type="info" size="small">该 Key 只能访问所选分组的上游源</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="addVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="adding" @click="handleAdd">
          {{ adding ? '添加中...' : '确定添加' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 修改 Key 弹窗 -->
    <BaseModal v-model:visible="editVisible" title="修改 API Key" size="wide">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="Key（不可改）">
          <el-input :model-value="editForm.key" disabled />
        </el-form-item>
        <el-form-item label="名称">
          <BaseInput v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="分组">
          <el-select v-model="editForm.groups" multiple placeholder="选择分组" style="width: 100%">
            <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="editForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="editVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="editing" @click="handleEditSave">
          {{ editing ? '保存中...' : '保存修改' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 接入说明弹窗 -->
    <BaseModal v-model:visible="usageVisible" :title="`接入说明：${usageKey?.name || ''}`" size="wide">
      <div v-if="usageKey" class="usage-body">
        <div class="usage-block">
          <div class="usage-label">请求地址（OpenAI 兼容）</div>
          <div class="usage-code-row">
            <code>{{ apiBase }}/v1/chat/completions</code>
            <BaseButton variant="ghost" size="sm" @click="copyText(`${apiBase}/v1/chat/completions`)">复制</BaseButton>
          </div>
          <el-text type="info" size="small">流式：请求体加 "stream": true；模型列表：GET {{ apiBase }}/v1/models</el-text>
        </div>

        <div class="usage-block">
          <div class="usage-label">鉴权（API Key）</div>
          <div class="usage-code-row">
            <code>Authorization: Bearer {{ usageKey.key }}</code>
            <BaseButton variant="ghost" size="sm" @click="copyText(usageKey.key)">复制 Key</BaseButton>
          </div>
        </div>

        <div class="usage-block">
          <div class="usage-label">该 Key 可用模型（分组：{{ (usageKey.groups || []).join('、') || 'free' }}）</div>
          <div v-if="usageModels.length" class="usage-models">
            <BaseBadge v-for="m in usageModels.slice(0, 30)" :key="m" variant="default" style="margin: 0 4px 4px 0">{{ m }}</BaseBadge>
            <el-text v-if="usageModels.length > 30" type="info" size="small">等共 {{ usageModels.length }} 个</el-text>
          </div>
          <el-text v-else type="info" size="small">该分组下暂无已配置模型的上游源；别名与聚合模型名也可作为 model 使用</el-text>
        </div>

        <div class="usage-block">
          <div class="usage-label-row">
            <span class="usage-label">curl 示例</span>
            <BaseButton variant="ghost" size="sm" @click="copyText(curlExample)">复制示例</BaseButton>
          </div>
          <pre class="usage-pre">{{ curlExample }}</pre>
        </div>

        <div class="usage-block">
          <div class="usage-label-row">
            <span class="usage-label">Python（OpenAI SDK）示例</span>
            <BaseButton variant="ghost" size="sm" @click="copyText(pythonExample)">复制示例</BaseButton>
          </div>
          <pre class="usage-pre">{{ pythonExample }}</pre>
        </div>
      </div>
    </BaseModal>
  </BaseSection>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import { addApiKey, deleteApiKey, listApiKeys, updateApiKey } from '@/api/apiKeys'
import { listUpstreams } from '@/api/upstreams'
import { reloadConfig } from '@/api/common'
import { listGroups } from '@/api/groups'
import { copyToClipboard } from '@/utils/clipboard'

const keys = ref<any[]>([])
const loading = ref(false)
const adding = ref(false)
const editing = ref(false)
const groupOptions = ref<{ name: string; description: string }[]>([])

const addVisible = ref(false)
const editVisible = ref(false)

// 接入说明弹窗
const usageVisible = ref(false)
const usageKey = ref<any>(null)
const upstreamList = ref<any[]>([])
const apiBase = location.origin

function openUsage(row: any) {
  usageKey.value = row
  usageVisible.value = true
}

const usageModels = computed<string[]>(() => {
  if (!usageKey.value) return []
  const groups = new Set(usageKey.value.groups || ['free'])
  const all = groups.has('*')
  const set = new Set<string>()
  for (const u of upstreamList.value) {
    if (!u.enabled) continue
    if (!all && !groups.has(u.group)) continue
    for (const m of u.models || []) {
      if (m?.name) set.add(m.name)
    }
  }
  return [...set].sort()
})

const demoModel = computed(() => usageModels.value[0] || 'deepseek-v4-flash')

const curlExample = computed(() => {
  if (!usageKey.value) return ''
  return `curl ${apiBase}/v1/chat/completions \\
  -H "Authorization: Bearer ${usageKey.value.key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"${demoModel.value}","messages":[{"role":"user","content":"你好"}]}'`
})

const pythonExample = computed(() => {
  if (!usageKey.value) return ''
  return `from openai import OpenAI

client = OpenAI(
    base_url="${apiBase}/v1",
    api_key="${usageKey.value.key}",
)

resp = client.chat.completions.create(
    model="${demoModel.value}",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)`
})

async function copyText(text: string) {
  const ok = await copyToClipboard(text)
  if (ok) ElMessage.success('已复制到剪贴板')
  else ElMessage.error('复制失败，请手动选择复制')
}

const addForm = reactive({ name: '', key: '', groups: ['free'] as string[] })
const editForm = reactive({ key: '', name: '', groups: [] as string[], enabled: true })

function genKey(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  let s = ''
  for (let i = 0; i < 28; i++) s += chars[Math.floor(Math.random() * chars.length)]
  return 'sk-sr-' + s
}

function regenerate() {
  addForm.key = genKey()
}

async function load() {
  loading.value = true
  try {
    const [res, groups, ups]: any = await Promise.all([listApiKeys(), listGroups(), listUpstreams()])
    keys.value = res.api_keys
    groupOptions.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
    upstreamList.value = ups.upstreams || []
  } finally {
    loading.value = false
  }
}

function openAdd() {
  addForm.name = ''
  addForm.key = genKey()
  addForm.groups = ['free']
  addVisible.value = true
}

function openEdit(row: any) {
  editForm.key = row.key
  editForm.name = row.name
  editForm.groups = [...(row.groups || [])]
  editForm.enabled = !!row.enabled
  editVisible.value = true
}

async function handleToggle(row: any) {
  await updateApiKey(row.key, { enabled: !row.enabled })
  ElMessage.success(row.enabled ? '已禁用' : '已启用')
  await reloadConfig()
  load()
}

function showCopy(row: any) {
  ElMessageBox.confirm(`完整 Key: ${row.key}\n复制后请妥善保管。`, '复制 Key', {
    confirmButtonText: '复制',
    cancelButtonText: '取消',
  })
    .then(async () => {
      const ok = await copyToClipboard(row.key)
      if (ok) ElMessage.success('已复制到剪贴板')
      else ElMessage.error('复制失败，请手动选择复制')
    })
    .catch(() => {})
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确定删除 Key「${row.name}」吗？删除后客户端将无法使用此 Key 访问。`, '删除确认', {
    type: 'warning',
  })
  await deleteApiKey(row.key)
  ElMessage.success('已删除')
  await reloadConfig()
  load()
}

async function handleAdd() {
  if (!addForm.key) {
    ElMessage.warning('Key 值为必填')
    return
  }
  adding.value = true
  try {
    await addApiKey({
      name: addForm.name || '未命名',
      key: addForm.key,
      groups: addForm.groups.length ? addForm.groups : ['free'],
    })
    ElMessage.success('API Key 添加成功')
    addVisible.value = false
    await reloadConfig()
    load()
  } finally {
    adding.value = false
  }
}

async function handleEditSave() {
  editing.value = true
  try {
    await updateApiKey(editForm.key, {
      name: editForm.name,
      groups: editForm.groups.length ? editForm.groups : ['free'],
      enabled: editForm.enabled,
    })
    ElMessage.success('API Key 修改成功')
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
.row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.key-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.key-input-row .base-input {
  flex: 1;
}
.usage-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.usage-label {
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 6px;
}
.usage-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.usage-label-row .usage-label {
  margin-bottom: 0;
}
.usage-code-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.usage-code-row code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.82rem;
  background: var(--bg-elevated);
  padding: 6px 10px;
  border-radius: 6px;
  word-break: break-all;
  flex: 1;
}
.usage-models {
  display: flex;
  flex-wrap: wrap;
}
.usage-pre {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
  background: var(--bg-elevated);
  padding: 10px 12px;
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre;
  margin: 0 0 6px;
  line-height: 1.6;
}
</style>
