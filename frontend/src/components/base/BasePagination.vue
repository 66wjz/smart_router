<template>
  <div v-if="show" class="base-pagination">
    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      :layout="layout"
      size="small"
      @current-change="onChange"
    />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  page: number
  pageSize: number
  total: number
  layout?: string
  /** 是否渲染（默认始终渲染，仅隐藏时由调用方传 false） */
  show?: boolean
}>(), {
  layout: 'prev, pager, next, total',
  show: true,
})

const emit = defineEmits<{
  'update:page': [value: number]
  change: [value: number]
}>()

function onChange(value: number) {
  emit('update:page', value)
  emit('change', value)
}
</script>

<style scoped>
.base-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
</style>
