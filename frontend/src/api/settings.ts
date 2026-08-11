import request from '@/utils/request'

export function getProbeConfig() {
  return request.get('/admin/api/config/probe')
}

export function saveProbeConfig(data: Record<string, unknown>) {
  return request.put('/admin/api/config/probe', data)
}

export function getRetryConfig() {
  return request.get('/admin/api/config/retry')
}

export function saveRetryConfig(data: Record<string, unknown>) {
  return request.put('/admin/api/config/retry', data)
}

export function getSmartRetryConfig() {
  return request.get('/admin/api/config/smart-retry')
}

export function saveSmartRetryConfig(data: Record<string, unknown>) {
  return request.put('/admin/api/config/smart-retry', data)
}

export function getFailoverConfig() {
  return request.get('/admin/api/config/failover')
}

export function saveFailoverConfig(data: Record<string, unknown>) {
  return request.put('/admin/api/config/failover', data)
}
