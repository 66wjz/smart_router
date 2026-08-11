import request from '@/utils/request'

export function getRules() {
  return request.get('/admin/api/rules')
}

export function saveRules(rules: unknown[]) {
  return request.put('/admin/api/rules', { rules })
}
