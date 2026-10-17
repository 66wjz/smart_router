import request from '@/utils/request'

export interface ModelEntry {
  name: string
  protocol?: 'openai' | 'anthropic' | 'responses'
  enabled?: boolean
}

export function listUpstreams() {
  return request.get('/admin/api/upstreams')
}

export function addUpstream(data: Record<string, unknown>) {
  return request.post('/admin/api/upstreams', data)
}

export function deleteUpstream(id: string) {
  return request.delete(`/admin/api/upstreams/${id}`)
}

export function updateUpstream(id: string, data: Record<string, unknown>) {
  return request.put(`/admin/api/upstreams/${id}`, data)
}

export function testUpstreamModel(id: string, data: { model: string; prompt?: string }) {
  return request.post(`/admin/api/upstreams/${id}/test`, data)
}

export function updateUpstreamModels(id: string, models: ModelEntry[]) {
  return request.put(`/admin/api/upstreams/${id}/models`, { models })
}

export function deleteUpstreamModel(id: string, model: string) {
  // 模型名可能含 /，走 query 参数避免路径匹配失败
  return request.delete(`/admin/api/upstreams/${id}/models`, { params: { model } })
}

export function toggleUpstreamModel(id: string, model: string, enabled: boolean) {
  // 模型名可能含 /，走 query 参数避免路径匹配失败（CH-019）
  return request.patch(`/admin/api/upstreams/${id}/models`, { enabled }, { params: { model } })
}

export function reorderUpstreamModels(id: string, names: string[]) {
  return request.put(`/admin/api/upstreams/${id}/models/order`, { names })
}
