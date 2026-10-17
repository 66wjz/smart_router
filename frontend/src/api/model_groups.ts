import request from '@/utils/request'

export interface ModelGroupSource {
  upstream: string
  weight?: number
}

export interface ModelGroup {
  model: string
  sources: string[]
  enabled: boolean
  configured: boolean
  auto_sources: string[]
}

export function listModelGroups() {
  return request.get('/admin/api/model-groups')
}

/** 模型名可能含 /，统一走 query 参数（后端参数名 model） */
export function saveModelGroup(model: string, upstreams: ModelGroupSource[], enabled: boolean) {
  return request.put('/admin/api/model-groups', { upstreams, enabled }, { params: { model } })
}

export function deleteModelGroup(model: string) {
  return request.delete('/admin/api/model-groups', { params: { model } })
}
