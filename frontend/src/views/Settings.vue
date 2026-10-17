<template>
  <div>
    <!-- 配置操作 -->
    <BaseSection variant="card" title="配置操作">
      <el-text type="info" size="small" style="margin-bottom: 12px; display: block">
        延迟探测、请求重试、智能重试、故障转移等路由相关参数已移至「智能路由 → 路由参数」。
      </el-text>
      <BaseButton variant="primary" :disabled="reloading" @click="handleReload">
        {{ reloading ? '热重载中...' : '热重载配置' }}
      </BaseButton>
    </BaseSection>

    <!-- 分组管理 -->
    <BaseSection variant="card" title="分组管理">
      <el-text type="info" size="small" style="margin-bottom: 12px; display: block">
        上游源和 API Key 按分组做权限隔离：API Key 只能访问其所属分组的上游源。被上游源或 API Key 引用的分组不可删除。
      </el-text>
      <el-table :data="groupsForm" size="small" style="margin-bottom: 12px">
        <el-table-column label="分组名" min-width="180">
          <template #default="{ row }">
            <BaseInput v-model="row.name" placeholder="如: free、premium" style="max-width: 240px" />
          </template>
        </el-table-column>
        <el-table-column label="描述" min-width="280">
          <template #default="{ row }">
            <BaseInput v-model="row.description" placeholder="分组说明（可选）" style="max-width: 360px" />
          </template>
        </el-table-column>
        <el-table-column label="" width="80" align="center">
          <template #default="{ $index }">
            <BaseButton variant="danger" size="sm" @click="removeGroup($index)">删除</BaseButton>
          </template>
        </el-table-column>
      </el-table>
      <div style="display: flex; gap: 8px; align-items: center">
        <BaseButton variant="ghost" size="sm" @click="addGroup">+ 添加分组</BaseButton>
        <BaseButton variant="primary" size="sm" :disabled="savingGroups" @click="handleSaveGroups">
          {{ savingGroups ? '保存中...' : '保存分组' }}
        </BaseButton>
      </div>
    </BaseSection>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { reloadConfig } from '@/api/common'
import { listGroups, updateGroups } from '@/api/groups'

const reloading = ref(false)
const savingGroups = ref(false)
const groupsForm = ref<{ name: string; description: string }[]>([])

async function load() {
  const groups: any = await listGroups()
  groupsForm.value = (groups.groups || []).map((g: any) => ({ name: g.name, description: g.description || '' }))
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

function addGroup() {
  groupsForm.value.push({ name: '', description: '' })
}

function removeGroup(index: number) {
  groupsForm.value.splice(index, 1)
}

async function handleSaveGroups() {
  const groups = groupsForm.value.filter((g) => g.name.trim())
  if (!groups.length) {
    ElMessage.warning('至少保留一个分组')
    return
  }
  savingGroups.value = true
  try {
    await updateGroups(groups)
    ElMessage.success('分组已保存')
    await reloadConfig()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存分组失败')
  } finally {
    savingGroups.value = false
  }
}

onMounted(load)
</script>
