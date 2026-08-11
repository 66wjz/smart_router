import request from '@/utils/request'

export function getAggregatedNames() {
  return request.get('/admin/api/aggregated-names')
}

export function saveAggregatedNames(names: string[]) {
  return request.put('/admin/api/aggregated-names', { names })
}

// 从上游源拉取模型列表（后端代理，避免跨域）
export function fetchUpstreamModels(upstreamId: string) {
  return request.get(`/admin/api/upstreams/${upstreamId}/models`, { timeout: 30000 })
}
