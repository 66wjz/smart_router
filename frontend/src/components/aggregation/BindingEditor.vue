<template>
  <div>
    <BaseNotice
      text="勾选本聚合要使用的规则；每条规则可只选部分候选。全选表示「跟随」——路由规则页以后新增的模型会自动纳入本聚合。"
    />
    <BaseEmptyState v-if="!catalog.length" description="路由规则页还没有候选，请先去配置" />

    <div v-for="(item, idx) in catalog" :key="item.name" class="bind-card">
      <div class="bind-head">
        <el-checkbox :model-value="item.used" @update:model-value="(v: any) => onUsedChange(idx, Boolean(v))">
          <span class="bind-rule-name">{{ item.name }}</span>
        </el-checkbox>
        <span class="bind-match">{{ matchText(item.match) }}</span>
        <span class="bind-count">
          {{ item.picked.length }} / {{ item.candidates.length }} 个候选
          <BaseBadge v-if="item.followAll && item.used" variant="green">跟随</BaseBadge>
        </span>
        <BaseButton v-if="item.used" variant="ghost" size="sm" @click="selectAll(idx, true)">全选</BaseButton>
        <BaseButton v-if="item.used && !item.followAll" variant="ghost" size="sm"
          @click="selectAll(idx, false)">清空</BaseButton>
      </div>
      <div v-if="item.used" class="bind-cands">
        <el-checkbox
          v-for="c in item.candidates"
          :key="candKey(c)"
          :model-value="item.picked.includes(candKey(c))"
          @update:model-value="() => toggleCandidate(idx, c)"
        >
          <span class="cand-src">{{ c.upstream }}</span>
          <code class="cand-model">{{ c.model }}</code>
          <span class="cand-meta">P{{ c.priority || 1 }} · 权重 {{ c.weight || 1 }}</span>
        </el-checkbox>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseEmptyState from '@/components/base/BaseEmptyState.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import { candKey, matchText, type BindItem } from './binding'

const props = defineProps<{
  catalog: BindItem[]
}>()

const emit = defineEmits<{
  'update:catalog': [value: BindItem[]]
}>()

function patch(idx: number, patchObj: Partial<BindItem>) {
  emit('update:catalog', props.catalog.map((it, i) => (i === idx ? { ...it, ...patchObj } : it)))
}

function onUsedChange(idx: number, used: boolean) {
  const item = props.catalog[idx]
  patch(idx, used
    ? { used: true, picked: item.candidates.map(candKey), followAll: true }
    : { used: false, picked: [], followAll: false })
}

function selectAll(idx: number, all: boolean) {
  const item = props.catalog[idx]
  patch(idx, { picked: all ? item.candidates.map(candKey) : [], followAll: all })
}

function toggleCandidate(idx: number, c: any) {
  const item = props.catalog[idx]
  const key = candKey(c)
  const picked = item.picked.includes(key)
    ? item.picked.filter((k) => k !== key)
    : [...item.picked, key]
  patch(idx, { picked, followAll: picked.length === item.candidates.length })
}
</script>

<style scoped>
.bind-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 10px;
  background: var(--bg-base);
}
.bind-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.bind-rule-name {
  font-weight: 600;
}
.bind-match {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}
.bind-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.bind-cands {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 8px;
  padding-left: 22px;
}
.cand-src {
  color: var(--text-tertiary);
  font-size: 0.78rem;
  margin-right: 6px;
}
.cand-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.76rem;
}
.cand-meta {
  color: var(--text-tertiary);
  font-size: 0.72rem;
  margin-left: 8px;
}
</style>
