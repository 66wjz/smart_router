<template>
  <div v-if="total > pageSize" class="base-pagination">
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
}>(), {
  layout: 'prev, pager, next, total',
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
