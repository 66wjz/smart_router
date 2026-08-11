<template>
  <BaseSection variant="card" title="聚合模型名管理">
    <el-alert
      title="聚合模型名是客户端请求时使用的统一模型名，路由代理会根据请求内容自动选择最佳模型。"
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
        <BaseButton variant="primary" :disabled="saving" @click="handleSave">
          {{ saving ? '保存中...' : '保存' }}
        </BaseButton>
      </el-form-item>
    </el-form>
  </BaseSection>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { getAggregatedNames, saveAggregatedNames } from '@/api/aggregated'
import { reloadConfig } from '@/api/common'

const names = ref<string[]>([])
const namesText = ref('')
const saving = ref(false)

async function load() {
  const res: any = await getAggregatedNames()
  names.value = res.names || []
  namesText.value = (res.names || []).join(', ')
}

async function handleSave() {
  const newNames = namesText.value
    .split(',')
    .map((n) => n.trim())
    .filter(Boolean)
  saving.value = true
  try {
    await saveAggregatedNames(newNames)
    ElMessage.success('聚合模型名已更新')
    await reloadConfig()
    load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

