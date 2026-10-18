<template>
  <BaseSection variant="card" title="上游源列表">
    <div class="toolbar">
      <BaseButton variant="primary" size="sm" @click="openAdd">+ 添加上游源</BaseButton>
    </div>

    <div v-loading="loading">
      <BaseEmptyState v-if="!upstreams.length && !loading" description="暂无上游源，请点击上方按钮添加" />
      <UpstreamCard
        v-for="u in upstreams"
        :key="u.id"
        :u="u"
        :toggling="togglingIds.includes(u.id)"
        @toggle="(v: boolean) => handleToggle(u, v)"
        @edit="openEdit(u)"
        @delete="handleDelete(u)"
        @manual-add="openManualModal(u)"
      />
    </div>

    <!-- 新增 / 修改上游源（共用表单） -->
    <UpstreamFormModal
      v-model:visible="formVisible"
      :mode="formMode"
      :form="form"
      :key-text="keyText"
      :group-options="groupOptions"
      :saving="formSaving"
      @update:form="Object.assign(form, $event)"
      @update:key-text="keyText = $event"
      @save="saveForm"
    />

    <!-- 手动添加模型弹窗 -->
    <BaseModal v-model:visible="manualModal.visible" title="手动添加模型" size="wide">
      <el-form :model="manualModal" label-width="90px">
        <el-form-item label="模型名" required>
          <BaseInput v-model="manualModal.input" placeholder="多个模型名用逗号分隔，如: gpt-4o, claude-3-5-sonnet" />
          <BaseHint text="已存在的模型名会自动跳过，不会重复添加" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseModalFooter :loading="manualModal.saving" confirm-text="添加" loading-text="添加中..."
          @cancel="manualModal.visible = false" @confirm="confirmManualAdd" />
      </template>
    </BaseModal>
  </BaseSection>
</template>

<script setup lang="ts">
import { onMounted, provide, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import UpstreamCard from '@/components/upstream/UpstreamCard.vue'
import UpstreamFormModal from '@/components/upstream/UpstreamFormModal.vue'
import { emptyForm, parseKeys, type UpstreamForm } from '@/components/upstream/form'
import { UPSTREAM_MODELS_KEY, useUpstreamModels } from '@/composables/useUpstreamModels'
import {
  addUpstream, deleteUpstream, listUpstreams, updateUpstream,
} from '@/api/upstreams'
import { reloadConfig } from '@/api/common'
import { listGroups } from '@/api/groups'

const upstreams = ref<any[]>([])
const loading = ref(false)
const groupOptions = ref<{ name: string; description: string }[]>([])
const togglingIds = ref<string[]>([])

// ---------- 新增/修改表单 ----------
const formVisible = ref(false)
const formMode = ref<'add' | 'edit'>('add')
const formSaving = ref(false)
const form = reactive<UpstreamForm>(emptyForm())
const keyText = ref('')

// ---------- 手动添加模型 ----------
const manualModal = reactive({ visible: false, uid: '', input: '', saving: false })

const models = useUpstreamModels(() => load())
provide(UPSTREAM_MODELS_KEY, models)

async function load() {
  loading.value = true
  try {
    const [res, groups]: any = await Promise.all([listUpstreams(), listGroups()])
    upstreams.value = res.upstreams
    groupOptions.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
    for (const u of res.upstreams) {
      models.setModels(u.id, u.models || [])
      models.initUpstream(u.id)
    }
  } finally {
    loading.value = false
  }
  models.initAllSortables(upstreams.value.map((u: any) => u.id))
}

function openAdd() {
  formMode.value = 'add'
  Object.assign(form, emptyForm())
  keyText.value = ''
  formVisible.value = true
}

function openEdit(u: any) {
  formMode.value = 'edit'
  Object.assign(form, {
    id: u.id,
    name: u.name,
    base_url: u.base_url,
    format: u.format,
    groups: u.groups && u.groups.length ? [...u.groups] : [u.group || 'free'],
    probe_enabled: !!u.probe_enabled,
    smart_retry: !!u.smart_retry,
  })
  keyText.value = (u.keys || []).join('\n')
  formVisible.value = true
}

async function saveForm() {
  if (formMode.value === 'add') {
    const keys = parseKeys(keyText.value)
    if (!form.id || !form.name || !form.base_url || !keys.length) {
      ElMessage.warning('ID、名称、Base URL、API Key 均为必填')
      return
    }
    formSaving.value = true
    try {
      await addUpstream({
        id: form.id,
        name: form.name,
        base_url: form.base_url,
        api_keys: keys,
        format: form.format,
        groups: form.groups.length ? form.groups : ['free'],
        probe_enabled: form.probe_enabled,
        smart_retry: form.smart_retry,
      })
      ElMessage.success(`上游源 ${form.id} 添加成功`)
      formVisible.value = false
      await reloadConfig()
      load()
    } finally {
      formSaving.value = false
    }
    return
  }

  if (!form.name || !form.base_url) {
    ElMessage.warning('名称和 Base URL 为必填')
    return
  }
  formSaving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: form.name,
      base_url: form.base_url,
      format: form.format,
      groups: form.groups.length ? form.groups : ['free'],
      probe_enabled: form.probe_enabled,
      smart_retry: form.smart_retry,
    }
    const keys = parseKeys(keyText.value)
    if (keys.length) payload.api_keys = keys
    await updateUpstream(form.id, payload)
    ElMessage.success(`上游源「${form.name}」修改成功`)
    formVisible.value = false
    await reloadConfig()
    load()
  } finally {
    formSaving.value = false
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
  manualModal.saving = true
  try {
    if (await models.addModels(manualModal.uid, names)) {
      ElMessage.success(`已添加 ${names.length} 个模型`)
      manualModal.visible = false
    }
  } finally {
    manualModal.saving = false
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
  if (!await confirmDanger(`确定删除上游源「${u.name}」吗？删除后引用它的路由候选将失效。`)) return
  await deleteUpstream(u.id)
  ElMessage.success('已删除')
  await reloadConfig()
  load()
}

onMounted(load)
</script>

<style scoped src="@/styles/upstreams.css"></style>
