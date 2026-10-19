<template>
  <BaseModal :visible="visible" :title="title" size="large" @update:visible="(v: boolean) => $emit('update:visible', v)">
    <el-form label-width="90px" style="margin-bottom: 12px">
      <el-form-item label="聚合名" required>
        <BaseInput :model-value="name" :disabled="mode === 'edit'"
          placeholder="客户端请求时使用的名字，如 deepseek-v4-1-flash"
          @update:model-value="(v: string) => $emit('update:name', v)" />
      </el-form-item>
      <el-form-item label="聚合类型" required>
        <el-radio-group :model-value="kind" :disabled="mode === 'edit'"
          @update:model-value="(v: any) => $emit('update:kind', v)">
          <el-radio value="static">固定成员（自己指定源与模型）</el-radio>
          <el-radio value="rule">规则匹配（复用路由规则，可裁剪）</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="可用分组">
        <el-select :model-value="groups" multiple clearable style="width: 100%"
          placeholder="不选 = 所有 Key 都可用"
          @update:model-value="(v: string[]) => $emit('update:groups', v)">
          <el-option v-for="g in groupOptions" :key="g.name" :label="g.name" :value="g.name" />
        </el-select>
        <BaseHint text="聚合是独立门面：此处分组决定哪些 API Key 能用它，成员所属上游源的分组不再参与校验" />
      </el-form-item>
    </el-form>

    <MemberEditor
      v-if="kind === 'static'"
      :items="items"
      :upstreams="upstreams"
      :source-models="sourceModels"
      @update:items="(v: MemberItem[]) => $emit('update:items', v)"
      @ensure-models="(u: string) => $emit('ensure-models', u)"
      @remove="(item: MemberItem) => $emit('remove-item', item)"
    />
    <BindingEditor
      v-else
      :catalog="catalog"
      @update:catalog="(v: BindItem[]) => $emit('update:catalog', v)"
    />

    <template #footer>
      <BaseModalFooter :loading="saving" @cancel="$emit('update:visible', false)" @confirm="$emit('save')" />
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseHint from '@/components/base/BaseHint.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseModalFooter from '@/components/base/BaseModalFooter.vue'
import MemberEditor from './MemberEditor.vue'
import BindingEditor from './BindingEditor.vue'
import type { BindItem, MemberItem } from './binding'

const props = defineProps<{
  visible: boolean
  mode: 'create' | 'edit'
  name: string
  kind: 'static' | 'rule'
  items: MemberItem[]
  catalog: BindItem[]
  upstreams: { id: string; name?: string }[]
  sourceModels: Record<string, string[]>
  /** CH-034：聚合可用分组（空 = 所有 Key 可用） */
  groups: string[]
  groupOptions: { name: string; description?: string }[]
  saving: boolean
}>()

defineEmits<{
  'update:visible': [value: boolean]
  'update:name': [value: string]
  'update:kind': [value: 'static' | 'rule']
  'update:items': [value: MemberItem[]]
  'update:catalog': [value: BindItem[]]
  'update:groups': [value: string[]]
  'ensure-models': [upstream: string]
  'remove-item': [item: MemberItem]
  save: []
}>()

const title = computed(() =>
  props.mode === 'create' ? '新建聚合' : `编辑聚合：${props.name}`)
</script>
