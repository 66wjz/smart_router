<template>
  <BaseSection
    variant="card"
    :title="title"
    :description="description"
  >
    <template v-if="$slots.actions" #actions>
      <slot name="actions" />
    </template>

    <!-- 顶部说明条（可选） -->
    <slot name="notice" />

    <!-- 筛选区 -->
    <div v-if="$slots.filters" class="lp-filters">
      <slot name="filters" />
    </div>

    <!-- 批量操作条：只有选中项时才由调用方渲染 -->
    <div v-if="$slots.toolbar" class="lp-toolbar">
      <slot name="toolbar" />
    </div>

    <!-- 表格区（或任意列表内容） -->
    <div class="lp-body" v-loading="loading">
      <slot />
    </div>

    <!--
      分页：CH-046 起空态也渲染。
      原来有 total > 0 判断，导致空列表时分页条整个消失，
      页面高度与「有数据时」不一致（用户反馈模型别名的空态就是这样）。
      只有显式 pagination=false 才不渲染。
    -->
    <TablePagination
      v-if="pagination"
      :page="page"
      :page-size="pageSize"
      :total="total"
      :page-sizes="pageSizes"
      :show-jumper="showJumper"
      @update:page="$emit('update:page', $event)"
      @update:page-size="$emit('update:pageSize', $event)"
      @change="$emit('page-change')"
    />
  </BaseSection>
</template>

<script setup lang="ts">
/**
 * 列表页骨架（CH-042 二级组件）
 *
 * 把「标题 + 右上操作 + 说明条 + 筛选 + 批量条 + 列表 + 分页」这套
 * 列表页的标准垂直结构固化下来。不走这个组件，就要手写 5 段重复代码。
 *
 * 刻意不做的事：
 *   - 不管数据获取（loading 由调用方控制）
 *   - 不管列定义（由 DataTable 承担）
 *   - 不强制一定用 DataTable（默认插槽可以是卡片列表）
 */
import BaseSection from '@/components/base/BaseSection.vue'
import TablePagination from './TablePagination.vue'

withDefaults(defineProps<{
  title?: string
  description?: string
  loading?: boolean
  /** 是否渲染分页；数据不足一页时也可置 false */
  pagination?: boolean
  page?: number
  pageSize?: number
  total?: number
  pageSizes?: number[]
  showJumper?: boolean
}>(), {
  title: '',
  description: '',
  loading: false,
  pagination: true,
  page: 1,
  pageSize: 20,
  total: 0,
  pageSizes: () => [20, 50, 100],
  showJumper: true,
})

defineEmits<{
  'update:page': [value: number]
  'update:pageSize': [value: number]
  'page-change': []
}>()
</script>

<style scoped>
.lp-filters {
  margin-bottom: 0;
}

.lp-toolbar {
  margin-top: 0;
}

.lp-body {
  min-height: 60px;
}
</style>
