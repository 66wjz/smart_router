<template>
  <BaseSection
    variant="card"
    title="模型别名管理"
    description="模型别名是指针：客户端请求别名时，直接转发到指定的真实模型，不走路由规则。可在后台随时切换指向。"
  >
    <div class="toolbar">
      <BaseButton variant="primary" size="sm" @click="openAdd">+ 新增别名</BaseButton>
    </div>

    <!-- 现有别名 -->
    <el-table :data="pointers" stripe v-loading="loading">
      <el-table-column prop="name" label="别名" width="200">
        <template #default="{ row }">
          <el-text type="primary" style="font-weight: 600">{{ row.name }}</el-text>
        </template>
      </el-table-column>
      <el-table-column prop="target_model" label="目标模型" min-width="240" />
      <el-table-column prop="upstream" label="上游源" width="120" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <BaseButton variant="ghost" size="sm" @click="openEdit(row)">修改</BaseButton>
          <BaseButton variant="danger" size="sm" @click="handleDelete(row)">删除</BaseButton>
        </template>
      </el-table-column>
      <template #empty>
        <BaseEmptyState description="暂无模型别名，请点击上方按钮新增" />
      </template>
    </el-table>

    <!-- 新增别名弹窗 -->
    <BaseModal v-model:visible="addVisible" title="新增别名" size="wide">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="别名名称" required>
          <BaseInput v-model="addForm.name" placeholder="例: my-model、gpt4" />
        </el-form-item>
        <el-form-item label="上游源" required>
          <el-select v-model="addForm.upstream" style="width: 100%" @change="onAddUpstreamChange">
            <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标模型" required>
          <el-select
            v-if="(modelsByUpstream[addForm.upstream] || []).length"
            v-model="addForm.target_model"
            filterable
            style="width: 100%"
          >
            <el-option v-for="m in modelsByUpstream[addForm.upstream]" :key="m" :label="m" :value="m" />
          </el-select>
          <BaseInput v-else v-model="addForm.target_model" placeholder="目标模型（手动输入）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="addVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="adding" @click="handleAdd">
          {{ adding ? '添加中...' : '确定添加' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- 修改别名弹窗 -->
    <BaseModal v-model:visible="editVisible" title="修改别名指向" size="wide">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="别名（不可改）">
          <el-input :model-value="editForm.name" disabled />
        </el-form-item>
        <el-form-item label="上游源" required>
          <el-select v-model="editForm.upstream" style="width: 100%" @change="onEditUpstreamChange">
            <el-option v-for="u in upstreamIds" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标模型" required>
          <el-select
            v-if="(modelsByUpstream[editForm.upstream] || []).length"
            v-model="editForm.target_model"
            filterable
            style="width: 100%"
          >
            <el-option v-for="m in modelsByUpstream[editForm.upstream]" :key="m" :label="m" :value="m" />
          </el-select>
          <BaseInput v-else v-model="editForm.target_model" placeholder="目标模型（手动输入）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <BaseButton variant="ghost" @click="editVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :disabled="editing" @click="handleEditSave">
          {{ editing ? '保存中...' : '保存修改' }}
        </BaseButton>
      </template>
    </BaseModal>
  </BaseSection>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import { confirmDanger } from '@/components/base/BaseConfirm'
import { addPointer, deletePointer, listPointers, updatePointer } from '@/api/pointers'
import { listUpstreams } from '@/api/upstreams'
import { fetchUpstreamModels } from '@/api/aggregated'
import { reloadConfig } from '@/api/common'

const pointers = ref<any[]>([])
const upstreamIds = ref<string[]>([])
const modelsByUpstream = reactive<Record<string, string[]>>({})
const loading = ref(false)
const adding = ref(false)
const editing = ref(false)

const addVisible = ref(false)
const editVisible = ref(false)

const editForm = reactive({ name: '', target_model: '', upstream: '' })
const addForm = reactive({ name: '', target_model: '', upstream: '' })

async function load() {
  loading.value = true
  try {
    const [ptRes, upsRes] = await Promise.all([listPointers(), listUpstreams()])
    pointers.value = (ptRes as any).pointers
    upstreamIds.value = (upsRes as any).upstreams.map((u: any) => u.id)
    if (upstreamIds.value.length && !addForm.upstream) addForm.upstream = upstreamIds.value[0]
    upstreamIds.value.forEach((id) => {
      fetchUpstreamModels(id)
        .then((r: any) => (modelsByUpstream[id] = r.models || []))
        .catch(() => {})
    })
  } finally {
    loading.value = false
  }
}

function openAdd() {
  addForm.name = ''
  addForm.target_model = ''
  addForm.upstream = upstreamIds.value[0] || ''
  addVisible.value = true
}

function openEdit(row: any) {
  editForm.name = row.name
  editForm.target_model = row.target_model
  editForm.upstream = row.upstream
  editVisible.value = true
}

function onAddUpstreamChange() {
  addForm.target_model = ''
}

function onEditUpstreamChange() {
  editForm.target_model = ''
}

async function handleAdd() {
  if (!addForm.name || !addForm.target_model) {
    ElMessage.warning('别名名称和目标模型为必填')
    return
  }
  adding.value = true
  try {
    await addPointer({ ...addForm })
    ElMessage.success(`别名 ${addForm.name} 添加成功`)
    addVisible.value = false
    await reloadConfig()
    load()
  } finally {
    adding.value = false
  }
}

async function handleEditSave() {
  if (!editForm.target_model) {
    ElMessage.warning('请选择目标模型')
    return
  }
  editing.value = true
  try {
    await updatePointer(editForm.name, { target_model: editForm.target_model, upstream: editForm.upstream })
    ElMessage.success(`别名 ${editForm.name} 已指向 ${editForm.target_model}`)
    editVisible.value = false
    await reloadConfig()
    load()
  } finally {
    editing.value = false
  }
}

async function handleDelete(row: any) {
  if (!await confirmDanger(`确定删除别名「${row.name}」吗？`)) return
  await deletePointer(row.name)
  ElMessage.success('已删除')
  await reloadConfig()
  load()
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
</style>
