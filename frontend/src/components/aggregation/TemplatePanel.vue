<template>
  <BaseSection variant="card" title="探测模板">
    <template #actions>
      <BaseButton variant="ghost" size="sm" @click="$emit('reload')">刷新</BaseButton>
      <BaseButton variant="primary" size="sm" @click="$emit('create')">+ 新建模板</BaseButton>
    </template>

    <BaseNotice
      text="模板 = 一套可复用的探测节奏（间隔 / 慢阈值 / 排序 / 时段）。多个聚合挂同一模板后共用同一节奏，改模板即全部生效；挂模板的聚合不再使用自己的探测参数。"
    />

    <div v-if="!templates.length" class="empty-tip">还没有探测模板。可以先建一个「标准-全天」模板，再挂到常用聚合上。</div>

    <el-table v-else :data="templates" size="small" stripe>
      <el-table-column label="模板名" min-width="160">
        <template #default="{ row }">
          <span class="tpl-name">{{ row.name }}</span>
          <span v-if="row.remark" class="tpl-remark"> {{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="间隔" width="90">
        <template #default="{ row }">{{ row.interval_seconds }}s</template>
      </el-table-column>
      <el-table-column label="慢阈值" width="90">
        <template #default="{ row }">
          {{ row.slow_threshold_seconds != null ? `${row.slow_threshold_seconds}s` : '跟随全局' }}
        </template>
      </el-table-column>
      <el-table-column label="排序" width="100">
        <template #default="{ row }">
          <BaseBadge :variant="row.sort_mode === 'latency' ? 'amber' : 'gray'">
            {{ row.sort_mode === 'latency' ? '速度优先' : '稳定优先' }}
          </BaseBadge>
        </template>
      </el-table-column>
      <el-table-column label="探测时段" min-width="180">
        <template #default="{ row }">{{ describeSchedule(row.schedule) }}</template>
      </el-table-column>
      <el-table-column label="被引用" min-width="200">
        <template #default="{ row }">
          <BaseBadge v-for="n in row.ref_names || []" :key="n" variant="blue" style="margin-right: 4px">{{ n }}</BaseBadge>
          <span v-if="!row.ref_count" class="muted">暂无聚合使用</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <BaseButton variant="ghost" size="sm" @click="$emit('edit', row)">编辑</BaseButton>
          <BaseButton variant="danger" size="sm" style="margin-left: 6px" @click="$emit('remove', row)">删除</BaseButton>
        </template>
      </el-table-column>
    </el-table>
  </BaseSection>
</template>

<script setup lang="ts">
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseNotice from '@/components/base/BaseNotice.vue'
import BaseSection from '@/components/base/BaseSection.vue'
import { describeSchedule } from './schedule'
import type { ProbeTemplate } from '@/api/aggregations'

defineProps<{
  templates: ProbeTemplate[]
}>()

defineEmits<{
  reload: []
  create: []
  edit: [row: ProbeTemplate]
  remove: [row: ProbeTemplate]
}>()
</script>

<style scoped>
.tpl-name {
  font-weight: 600;
}
.tpl-remark {
  color: var(--text-tertiary);
  margin-left: 8px;
  font-size: 0.78rem;
}
.muted {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}
.empty-tip {
  padding: 8px 0;
  font-size: 0.82rem;
  color: var(--text-tertiary);
}
</style>
