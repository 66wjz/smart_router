import request from '@/utils/request'

export function listGroups() {
  return request.get('/admin/api/groups')
}

export function updateGroups(groups: { name: string; description: string }[]) {
  return request.put('/admin/api/groups', { groups })
}
