<template>
  <div class="chip-flow">
    <div class="cf-track">
      <template v-for="(item, i) in pageItems" :key="chipKey(item, indexOf(i))">
        <span class="cf-chip" :class="{ 'is-first': showFirstLastTag && indexOf(i) === 0 }">
          <span v-if="showIndex" class="cf-index">{{ indexOf(i) + 1 }}</span>
          <span class="cf-src">{{ renderUpstream(item) }}</span>
          <code class="cf-model">{{ renderModel(item) }}</code>
          <span v-if="metaText(item)" class="cf-meta">{{ metaText(item) }}</span>
          <span v-if="showFirstLastTag && indexOf(i) === 0" class="cf-tag-first">首选</span>
          <span
            v-else-if="showFirstLastTag && indexOf(i) === items.length - 1"
            class="cf-tag-last"
          >兜底</span>
        </span>
        <span v-if="arrow && i < pageItems.length - 1" class="cf-arrow">→</span>
      </template>
      <span v-if="!items.length" class="cf-empty">{{ emptyText }}</span>
    </div>

    <!--
      分页：与 TablePagination 同一套形态（共 N 个 + 页码）
      只在 pager=true 且超过一页时出现。
      CH-044：聚合模型页改为「列表级分页」后，卡片内不再自建分页（pager=false 平铺全部）。
    -->
    <div v-if="pager && totalPages > 1" class="cf-pager">
      <span class="cf-total">共 {{ items.length }} 个</span>
      <button
        type="button" class="cf-btn" :disabled="page === 1"
        @click="page--"
      >‹</button>
      <button
        v-for="p in totalPages" :key="p"
        type="button" class="cf-btn" :class="{ active: p === page }"
        @click="page = p"
      >{{ p }}</button>
      <button
        type="button" class="cf-btn" :disabled="page === totalPages"
        @click="page++"
      >›</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 只读成员流（CH-043 二级组件）
 *
 * 为什么要抽：
 *   「上游源 / 聚合成员 / 疑似合并成员」三处的成员集合长得一样，
 *   却各写了一套（.source-flow / .suggest-members / .grp-flow / .dp-model-chips），
 *   chip 样式也有四份。这里收成一份。
 *
 * 为什么用「分页」而不是「展开/收起」：
 *   用户明确要求与列表组件的形态一致 —— 底部显示「共 N 个 + 页码」切换，
 *   这样成员多的聚合、疑似合并建议看起来和普通列表是一个体系。
 */
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  items: any[]
  pageSize?: number
  chipKey?: (item: any, index: number) => string
  renderUpstream?: (item: any) => string
  renderModel?: (item: any) => string
  /** CH-051：chip 尾部的附加标记（如聚合成员的权重 ×2），空串不渲染 */
  renderMeta?: (item: any) => string
  showIndex?: boolean
  /** 首个标「首选」、末个标「兜底」（聚合链路用） */
  showFirstLastTag?: boolean
  arrow?: boolean
  emptyText?: string
  /**
   * 是否在组件内部翻页（默认 false = 全部平铺）。
   * CH-044：卡片作为列表条目时，分页应由列表页统一承担，
   * 否则同一个页面会出现「列表分页 + 卡片内分页」两套页码。
   */
  pager?: boolean
}>(), {
  pageSize: 10,
  chipKey: undefined,
  renderUpstream: (item: any) => item?.upstream_name || item?.upstream || '',
  renderModel: (item: any) => item?.model || '',
  renderMeta: undefined,
  showIndex: true,
  showFirstLastTag: false,
  arrow: false,
  emptyText: '没有任何可用成员',
  pager: false,
})

const page = ref(1)

const totalPages = computed(() =>
  Math.max(1, Math.ceil((props.items?.length || 0) / props.pageSize)),
)

const pageItems = computed(() => {
  if (!props.pager) return props.items || []
  const start = (page.value - 1) * props.pageSize
  return (props.items || []).slice(start, start + props.pageSize)
})

/** 当前页第 i 项在整体中的下标 —— 序号要连续，不能每页从 1 开始 */
function indexOf(i: number): number {
  if (!props.pager) return i
  return (page.value - 1) * props.pageSize + i
}

function chipKey(item: any, index: number): string {
  if (props.chipKey) return props.chipKey(item, index)
  return `${item?.upstream || ''}::${item?.model || ''}::${index}`
}

function metaText(item: any): string {
  return props.renderMeta ? String(props.renderMeta(item) || '') : ''
}

// 成员集合变化（如切换聚合、重新拉取）时回到第一页，
// 否则可能停在一个已不存在的页码上
watch(() => props.items, () => { page.value = 1 })
</script>

<style scoped>
.chip-flow {
  margin-top: 10px;
}

.cf-track {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.cf-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-hover);
  font-size: 12.5px;
  max-width: 100%;
}

/* 链路首个成员高亮，和原先 .source-chip.is-first 保持一致 */
.cf-chip.is-first {
  background: var(--accent-green-muted);
}

.cf-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border-radius: 50%;
  background: var(--bg-base);
  font-size: 11px;
  color: var(--text-tertiary);
}

.cf-src {
  color: var(--text-secondary);
  white-space: nowrap;
}

.cf-meta {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--accent-amber-muted, rgba(245, 158, 11, 0.15));
  color: var(--accent-amber);
  font-size: 11px;
  white-space: nowrap;
}

.cf-model {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.cf-tag-first {
  color: var(--accent-green);
  font-size: 11px;
}

.cf-tag-last {
  color: var(--text-tertiary);
  font-size: 11px;
}

.cf-arrow {
  color: var(--text-tertiary);
  font-size: 12px;
}

.cf-empty {
  font-size: 12.5px;
  color: var(--accent-amber);
}

/* ---------- 分页 ---------- */
.cf-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 10px;
}

.cf-total {
  font-size: 13px;
  color: var(--text-secondary);
  margin-right: 6px;
}

.cf-btn {
  min-width: 24px;
  height: 24px;
  padding: 0 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-base);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--duration-fast);
}

.cf-btn:hover:not(:disabled) {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.cf-btn.active {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
}

.cf-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
