<template>
  <div class="stat-card" :class="'tone-' + tone">
    <div class="sc-label">
      {{ label }}
      <el-tooltip v-if="hint" :content="hint" placement="top">
        <span class="sc-tip">?</span>
      </el-tooltip>
    </div>
    <div class="sc-value">
      <slot>{{ value }}</slot>
    </div>
    <div v-if="sub" class="sc-sub">{{ sub }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * 指标卡（CH-042 二级组件）
 *
 * 解决现状：Dashboard 用 `.metric-card/.mc-label/.mc-value`，
 * Usage 用 `.metric-label/.metric-value` —— 同一件东西两份样式。
 * 这里用同一套语义色（tone）+ 同一套字号节奏。
 */
import type { StatTone } from './types'

withDefaults(defineProps<{
  label: string
  value?: string | number
  tone?: StatTone
  /** 悬浮说明，展示为右上角 ? */
  hint?: string
  /** 数值下方的补充说明 */
  sub?: string
}>(), {
  value: '',
  tone: 'default',
  hint: '',
  sub: '',
})
</script>

<style scoped>
.stat-card {
  padding: 14px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
  background: var(--bg-base);
  min-width: 0;
}

.sc-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}

.sc-tip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  font-size: 10px;
  cursor: help;
  flex-shrink: 0;
}

.sc-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 语义色只作用于数值，标签保持中性，避免整卡变色显得吵 */
.tone-primary .sc-value { color: var(--accent-blue); }
.tone-success .sc-value { color: var(--accent-green); }
.tone-warning .sc-value { color: var(--accent-amber); }
.tone-danger .sc-value { color: var(--accent-red); }
</style>
