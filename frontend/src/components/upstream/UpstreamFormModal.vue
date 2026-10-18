<template>
  <BaseModal :visible="visible" :title="mode === 'add' ? '添加上游源' : '修改上游源'" size="wide"
    @update:visible="(v: boolean) => $emit('update:visible', v)">
    <el-form :model="form" label-width="90px">
      <el-form-item label="ID（唯一）" :required="mode === 'add'">
        <el-input v-if="mode === 'edit'" :model-value="form.id" disabled />
        <BaseInput v-else :model-value="form.id" placeholder="例: newapi、xiaomi"
          @update:model-value="(v: string) => patch({ id: v })" />
      </el-form-item>

      <el-form-item label="显示名称" required>
        <BaseInput :model-value="form.name" placeholder="例: NewAPI 中转站"
          @update:model-value="(v: string) => patch({ name: v })" />
      </el-form-item>

      <el-form-item label="Base URL" required>
        <BaseInput :model-value="form.base_url" placeholder="http://..."
          @update:model-value="(v: string) => patch({ base_url: v })" />
        <div v-if="form.base_url.trim()" class="url-preview">
          <div>实际请求地址：<code>{{ buildEndpointPreview(form.base_url, form.format === 'anthropic' ? '/v1/messages' : '/v1/chat/completions') }}</code></div>
          <div>模型列表地址：<code>{{ buildEndpointPreview(form.base_url, '/v1/models') }}</code></div>
        </div>
      </el-form-item>

      <el-form-item label="API Key" :required="mode === 'add'">
        <el-input
          :model-value="keyText"
          type="textarea"
          :rows="3"
          :placeholder="mode === 'add'
            ? '每行一个 API Key，支持批量粘贴\n多个 Key 自动轮询分摊流量'
            : '每行一个 API Key\n留空表示不修改 Key 池'"
          @update:model-value="(v: string) => $emit('update:keyText', v)"
        />
        <BaseHint :text="mode === 'add'
          ? '可填写多个 Key（每行一个），请求自动轮询；单个 Key 失败/限流自动换下一个'
          : '回显现有 Key（每行一个）；清空则保持原 Key 池不变；非空则整体替换'" />
      </el-form-item>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="默认协议">
            <el-select :model-value="form.format" style="width: 100%"
              @update:model-value="(v: string) => patch({ format: v })">
              <el-option label="openai" value="openai" />
              <el-option label="anthropic" value="anthropic" />
            </el-select>
            <BaseHint text="该源模型默认使用的协议；单个模型可在模型列表中单独覆盖" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="分组">
            <el-select :model-value="form.groups" multiple placeholder="可多选，任意一个分组的 Key 都可访问本源" style="width: 100%"
              @update:model-value="(v: string[]) => patch({ groups: v })">
              <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="延迟探测">
        <el-switch :model-value="form.probe_enabled"
          @update:model-value="(v: any) => patch({ probe_enabled: Boolean(v) })" />
      </el-form-item>

      <el-form-item label="智能重试">
        <el-switch :model-value="form.smart_retry"
          @update:model-value="(v: any) => patch({ smart_retry: Boolean(v) })" />
        <BaseHint text="开启后，5xx/超时/连接中断自动换 Key 或退避重试，客户端无感知。适合 opencode 等不稳定上游"
          style="margin-left: 8px" />
      </el-form-item>
    </el-form>

    <template #footer>
      <BaseModalFooter
        :loading="saving"
        :confirm-text="mode === 'add' ? '确定添加' : '保存修改'"
        :loading-text="mode === 'add' ? '添加中...' : '保存中...'"
        @cancel="$emit('update:visible', false)"
        @confirm="$emit('save')"
      />
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import BaseHint from '@/components/base/BaseHint.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import { buildEndpointPreview, type UpstreamForm } from './form'

const props = defineProps<{
  visible: boolean
  mode: 'add' | 'edit'
  form: UpstreamForm
  keyText: string
  groupOptions: { name: string; description: string }[]
  saving: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:form': [value: UpstreamForm]
  'update:keyText': [value: string]
  save: []
}>()

function patch(patchObj: Partial<UpstreamForm>) {
  emit('update:form', { ...props.form, ...patchObj })
}
</script>

<style scoped>
.url-preview {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--bg-elevated);
  border-radius: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.7;
  width: 100%;
}
.url-preview code {
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text-primary);
  word-break: break-all;
}
</style>
