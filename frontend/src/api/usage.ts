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
