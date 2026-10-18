<template>
  <div class="group-card">
    <div class="group-head">
      <div class="group-title">
        <code class="group-model">{{ g.name }}</code>
        <BaseBadge :variant="g.kind === 'rule' ? 'purple' : 'blue'">
          {{ g.kind === 'rule' ? '规则匹配' : '固定成员' }}
        </BaseBadge>
        <BaseBadge v-if="!g.configured" variant="gray">自动发现</BaseBadge>
        <BaseBadge v-if="g.template_name" variant="green">模板: {{ g.template_name }}</BaseBadge>
        <BaseBadge :variant="g.probe.sort_mode === 'latency' ? 'amber' : 'gray'">
          {{ g.probe.sort_mode === 'latency' ? '速度优先' : '稳定优先' }}
        </BaseBadge>
        <BaseBadge :variant="probeBadge.variant">{{ probeBadge.text }}</BaseBadge>
        <BaseBadge v-if="!g.enabled" variant="red">聚合已关闭</BaseBadge>
      </div>
      <div class="group-ops">
        <span class="op-label">启用</span>
        <el-switch
          :model-value="g.enabled"
          size="small"
          :disabled="saving"
          @change="(val: boolean | string | number) => $emit('toggle', Boolean(val))"
        />
        <BaseButton variant="ghost" size="sm" @click="$emit('probe')">探测设置</BaseButton>
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
      </div>
    </div>

    <!-- 固定成员：候选链路 -->
    <div v-if="g.kind === 'static'" class="source-flow">
      <template v-for="(m, i) in g.members" :key="m.upstream + (m.model || '')">
        <span class="source-chip" :class="{ 'is-first': i === 0 }">
          <span class="chip-index">{{ i + 1 }}</span>
          <span class="chip-src">{{ m.upstream }}</span>
          <code class="chip-model">{{ m.model || g.name }}</code>
          <span v-if="i === 0" class="tag-first">首选</span>
          <span v-else-if="i === g.members.length - 1" class="tag-last">兜底</span>
        </span>
        <span v-if="i < g.members.length - 1" class="arrow">→</span>
      </template>
      <span v-if="!g.members.length" class="empty-tip">没有任何可用成员</span>
    </div>

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

    <div v-if="!g.enabled" class="group-warn">
      {{ g.kind === 'rule'
        ? '聚合已关闭：客户端请求该名字将不再走规则路由。'
        : '聚合已关闭：请求该名字时只走第一个可用成员，不做跨源兜底。' }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import type { Aggregation } from '@/api/aggregations'

type BadgeVariant = 'default' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'gray'

const props = defineProps<{
  g: Aggregation
  saving: boolean
}>()

defineEmits<{
  toggle: [enabled: boolean]
  probe: []
  edit: []
  remove: []
  reset: []
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
.group-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 12px;
  background: var(--bg-base);
}
.group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.group-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.95rem;
  font-weight: 600;
}
.group-ops {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.op-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}
.source-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.source-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-hover);
  font-size: 0.8rem;
}
.source-chip.is-first {
  background: var(--accent-green-muted, rgba(103, 194, 58, 0.12));
}
.chip-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-base);
  font-size: 0.7rem;
}
.chip-src {
  color: var(--text-secondary, var(--text-tertiary));
}
.chip-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.75rem;
}
.tag-first {
  color: var(--accent-green);
  font-size: 0.72rem;
}
.tag-last {
  color: var(--text-tertiary);
  font-size: 0.72rem;
}
.arrow {
  color: var(--text-tertiary);
  font-size: 0.85rem;
}
.rule-flow {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
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
  margin-top: 8px;
  font-size: 0.78rem;
  color: var(--accent-amber);
}
.empty-tip {
  padding: 8px 0;
  font-size: 0.8rem;
  color: var(--accent-amber);
}
</style>
