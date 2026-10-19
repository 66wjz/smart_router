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

/** 单条请求详情：summary + attempts + detail（三栏报文，CH-038） */
export function getUsageLogDetail(logId: number) {
  return request.get(`/admin/api/usage/logs/${logId}`)
}

/** 详情采集策略：mode / max_bytes / retention_days（CH-038） */
export function getUsageDetailConfig() {
  return request.get('/admin/api/config/usage-detail')
}

export function saveUsageDetailConfig(data: {
  mode: string
  max_bytes?: number
  retention_days?: number
}) {
  return request.put('/admin/api/config/usage-detail', data)
}
