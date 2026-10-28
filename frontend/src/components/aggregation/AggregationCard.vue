<template>
  <EntityCard
    :data-agg-name="g.name"
    :disabled="!g.enabled"
    selectable
    :checked="checked"
    @update:checked="(v: boolean) => $emit('update:checked', v)"
  >
    <template #title>
      <code class="group-model">{{ g.name }}</code>
      <BaseBadge :variant="g.kind === 'rule' ? 'purple' : 'blue'">
        {{ g.kind === 'rule' ? '规则匹配' : '固定成员' }}
      </BaseBadge>
      <BaseBadge v-if="!g.configured" variant="gray">自动发现</BaseBadge>
      <BaseBadge variant="purple">
        {{ (g.groups && g.groups.length) ? `分组: ${g.groups.join('/')}` : '所有分组可用' }}
      </BaseBadge>
      <BaseBadge v-if="g.template_name" variant="green">模板: {{ g.template_name }}</BaseBadge>
      <BaseBadge :variant="g.probe.sort_mode === 'latency' ? 'amber' : 'gray'">
        {{ g.probe.sort_mode === 'latency' ? '速度优先' : '稳定优先' }}
      </BaseBadge>
      <BaseBadge :variant="probeBadge.variant">{{ probeBadge.text }}</BaseBadge>
      <BaseBadge v-if="!g.enabled" variant="red">聚合已关闭</BaseBadge>
    </template>

    <template #actions>
      <span class="op-label">启用</span>
      <el-switch
        :model-value="g.enabled"
        size="small"
        :disabled="saving"
        @change="(val: boolean | string | number) => $emit('toggle', Boolean(val))"
      />
      <BaseButton variant="ghost" size="sm" @click="$emit('probe')">探测设置</BaseButton>
      <BaseButton v-if="g.configured" variant="ghost" size="sm" :disabled="!g.enabled || saving"
        @click="$emit('test')">
        测试
      </BaseButton>
      <BaseButton v-if="g.kind === 'static'" variant="primary" size="sm" :disabled="saving"
        @click="$emit('edit')">
        {{ saving ? '保存中…' : '编辑成员' }}
      </BaseButton>
      <BaseButton v-else variant="primary" size="sm" :disabled="saving" @click="$emit('edit')">
        {{ saving ? '保存中…' : '编辑绑定' }}
      </BaseButton>
      <BaseButton v-if="g.kind === 'rule' || !g.configured" variant="danger" size="sm"
        :disabled="saving" @click="$emit('remove')">移除</BaseButton>
      <BaseButton v-else variant="ghost" size="sm" :disabled="saving" @click="$emit('reset')">恢复自动</BaseButton>
    </template>

    <!-- 固定成员：候选链路（CH-044 起卡片内平铺全部成员，分页交给外层列表）
         CH-051：权重 >1 的成员带 ×N 角标；首位由权重轮换决定，不再标「首选」 -->
    <ChipFlow
      v-if="g.kind === 'static'"
      :items="g.members"
      :render-meta="(m: any) => (m.weight && m.weight > 1 ? '×' + m.weight : '')"
      arrow
    />

    <!-- 规则聚合：绑定的规则与候选 -->
    <div v-else class="rule-flow">
      <span class="rule-hint">
        {{ g.rule_bindings ? '按绑定的规则与候选路由：' : '候选由路由规则决定，运行时按请求内容匹配：' }}
      </span>
      <BaseBadge v-for="item in (g.rule_binding_summary?.items || [])" :key="item.rule" variant="purple">
        {{ item.rule }}({{ item.count }}{{ item.follow_all ? ' · 跟随' : '' }})
      </BaseBadge>
      <BaseBadge v-for="r in (g.rule_bindings ? [] : (g.rule_names || []))" :key="'r-' + r"
        variant="purple">{{ r }}</BaseBadge>
      <span class="rule-cost">
        {{ g.rule_binding_summary
          ? `${g.rule_binding_summary.rule_count} 条规则 · ${g.rule_binding_summary.candidate_count} 个候选 · `
          : '' }}覆盖 {{ g.member_count }} 个探测单元
      </span>
      <BaseBadge v-if="(g.stale_bindings || []).length" variant="amber">
        {{ (g.stale_bindings || []).length }} 个绑定已失效
      </BaseBadge>
    </div>

    <template v-if="!g.enabled" #footer>
      <span class="group-warn">
        {{ g.kind === 'rule'
          ? '聚合已关闭：客户端请求该名字将不再走规则路由。'
          : '聚合已关闭：请求该名字时只走第一个可用成员，不做跨源兜底。' }}
      </span>
    </template>
  </EntityCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import ChipFlow from '@/components/base/ChipFlow.vue'
import EntityCard from '@/components/base/EntityCard.vue'
import type { Aggregation } from '@/api/aggregations'

type BadgeVariant = 'default' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'gray'

const props = defineProps<{
  g: Aggregation
  saving: boolean
  /** 列表页统一管理的勾选态（CH-044） */
  checked?: boolean
}>()

defineEmits<{
  toggle: [enabled: boolean]
  probe: []
  test: []
  edit: []
  remove: []
  reset: []
  'update:checked': [value: boolean]
}>()

const probeBadge = computed<{ text: string; variant: BadgeVariant }>(() => {
  const g = props.g
  if (!g.probe.enabled) return { text: '探测: 关', variant: 'gray' }
  const sched = g.probe.schedule?.mode === 'window' ? ' · 限时段' : ''
  const src = g.template_name ? '模板' : g.self_config.interval_seconds ? '' : '全局'
  return { text: `探测: 开 · ${src}${g.probe.interval_seconds}s${sched}`, variant: 'green' }
})
</script>

<style scoped>
/* 卡片外壳由 EntityCard 统一（CH-043），这里只保留本组件特有的部分 */
/* CH-044：拖拽手柄已移除（分页后只调当页会歧义），对应 .drag-handle / .drag-ghost 样式一并清掉 */

.group-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.95rem;
  font-weight: 600;
}

.op-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.rule-flow {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 0.8rem;
}
.rule-hint,
.rule-cost {
  color: var(--text-tertiary);
}
.rule-cost {
  font-size: 0.75rem;
}
.group-warn {
  color: var(--accent-amber);
}
</style>
