import request from '@/utils/request'

export function getUsageSummary(range: string) {
  return request.get('/admin/api/usage/summary', { params: { range } })
}

export function getUsageByModel(range: string) {
  return request.get('/admin/api/usage/by-model', { params: { range } })
}

export function getUsageByKey(range: string) {
  return request.get('/admin/api/usage/by-key', { params: { range } })
}

/** 按「上游源 × 上游真实模型名」聚合（号池消耗核算，CH-021） */
export function getUsageByUnit(range: string) {
  return request.get('/admin/api/usage/by-unit', { params: { range } })
}

export function getUsageLogs(params: {
  range: string
  page?: number
  size?: number
  key_id?: number
  model?: string
  status?: string
}) {
  return request.get('/admin/api/usage/logs', { params })
}
