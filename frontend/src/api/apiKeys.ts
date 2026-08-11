import request from '@/utils/request'

export function listApiKeys() {
  return request.get('/admin/api/api-keys')
}

export function addApiKey(data: { name: string; key: string; groups?: string[]; enabled?: boolean }) {
  return request.post('/admin/api/api-keys', data)
}

export function updateApiKey(key: string, data: { name?: string; groups?: string[]; enabled?: boolean }) {
  return request.put(`/admin/api/api-keys/${encodeURIComponent(key)}`, data)
}

export function deleteApiKey(key: string) {
  return request.delete(`/admin/api/api-keys/${encodeURIComponent(key)}`)
}
