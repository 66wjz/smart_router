<template>
  <div class="entity-card" :class="{ 'is-disabled': disabled, 'is-selected': selectable && checked }">
    <div class="ec-head">
      <!-- 列表级多选：勾选框挂在卡片左侧，由列表页统一管理选中集合 -->
      <el-checkbox
        v-if="selectable"
        class="ec-check"
        :model-value="checked"
        :disabled="disabled"
        @change="(v: any) => $emit('update:checked', Boolean(v))"
      />
      <div class="ec-title">
        <slot name="title" />
      </div>
      <div v-if="$slots.actions" class="ec-actions">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="$slots.meta" class="ec-meta">
      <slot name="meta" />
    </div>

    <div v-if="$slots.default" class="ec-body">
      <slot />
    </div>

    <div v-if="$slots.footer" class="ec-foot">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 主从卡片外壳（CH-043 二级组件）
 *
 * 为什么抽：
 *   上游源 / 聚合模型 / 疑似同一模型 三处卡片结构同源，
 *   却各写了一套外壳（6 份：.upstream-card / .group-card / .suggest-card
 *   / 仪表盘 .up-card 与 .grp-card / 预览页 .dp-card），
 *   padding 12/14/16 三种、间距也各不相同。
 *
 * 统一口径：radius = --radius-md，padding = 14px，卡片间距 = 12px。
 * 想调某处整体密度时只改这里，不用挨个找。
 *
 * CH-044：加可选勾选框。聚合模型页本质是一个「条目为卡片的列表」，
 * 选中与批量操作归列表页管，卡片只负责把勾选位置让出来。
 */
withDefaults(defineProps<{
  disabled?: boolean
  /** 是否显示勾选框（列表页有批量操作时打开） */
  selectable?: boolean
  /** 当前是否勾选 */
  checked?: boolean
}>(), {
  disabled: false,
  selectable: false,
  checked: false,
})

defineEmits<{
  'update:checked': [value: boolean]
}>()
</script>

<style scoped>
.entity-card {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 14px;
  margin-bottom: 12px;
  background: var(--bg-base);
}

/* 禁用态：整卡降透明度，与上游源卡片原有表现一致 */
.entity-card.is-disabled {
  opacity: 0.55;
  background: var(--bg-elevated);
}

/* CH-044：勾选态给一道浅蓝边，和 el-table 的多选观感对齐 */
.entity-card.is-selected {
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 1px var(--accent-blue-muted, rgba(64, 158, 255, 0.12));
}

.ec-check {
  flex: 0 0 auto;
  margin-right: 2px;
}

.ec-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ec-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  /* 占满中间剩余空间，把操作区推到最右（否则 space-between 会把标题挤到中间） */
  flex: 1;
  min-width: 0;
}

.ec-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ec-meta {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* 正文与标题区之间留出呼吸，避免成员流贴太紧 */
.ec-body {
  margin-top: 10px;
}

.ec-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-subtle);
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
