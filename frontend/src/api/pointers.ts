import request from '@/utils/request'

export function listPointers() {
  return request.get('/admin/api/model-pointers')
}

export function addPointer(data: { name: string; target_model: string; upstream?: string }) {
  return request.post('/admin/api/model-pointers', data)
}

export function updatePointer(name: string, data: { target_model?: string; upstream?: string }) {
  return request.put(`/admin/api/model-pointers/${encodeURIComponent(name)}`, data)
}

export function deletePointer(name: string) {
  return request.delete(`/admin/api/model-pointers/${encodeURIComponent(name)}`)
}
