import request from '@/utils/request'

export function listFilterRules() {
  return request.get('/admin/api/filter-rules')
}

export function addFilterRule(data: any) {
  return request.post('/admin/api/filter-rules', data)
}

export function updateFilterRule(id: number, data: any) {
  return request.put(`/admin/api/filter-rules/${id}`, data)
}

export function deleteFilterRule(id: number) {
  return request.delete(`/admin/api/filter-rules/${id}`)
}

export function setFilterEngine(enabled: boolean) {
  return request.put('/admin/api/filter-rules/engine', { enabled })
}

/** 试跑：传入请求体，返回会命中哪些规则（不改变任何状态） */
export function testFilterRules(data: { body: any; upstream_ids?: string[] }) {
  return request.post('/admin/api/filter-rules/test', data)
}
