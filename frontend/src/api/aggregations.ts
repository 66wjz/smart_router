import request from '@/utils/request'

// ---------- 类型 ----------

export interface ProbeWindow {
  start: string
  end: string
}

export interface ProbeSchedule {
  mode: 'always' | 'window'
  days: number[]
  windows: ProbeWindow[]
}

export interface AggregationMember {
  upstream: string
  /** 该上游源里的真实模型名；为空表示与聚合名同名 */
  model?: string | null
  weight?: number
}

export interface AggregationProbe {
  enabled: boolean
  interval_seconds: number
  slow_threshold_seconds: number | null
  sort_mode: 'stable' | 'latency'
  schedule: ProbeSchedule
  template_id: number | null
  template_name: string
}

export interface Aggregation {
  name: string
  kind: 'static' | 'rule'
  enabled: boolean
  /** 未人工配置、由同名模型自动发现时为 false */
  configured: boolean
  members: AggregationMember[]
  member_count: number
  template_id: number | null
  template_name: string
  probe: AggregationProbe
  self_config: {
    probe_enabled: boolean
    interval_seconds: number | null
    slow_threshold_seconds: number | null
    sort_mode: 'stable' | 'latency'
    schedule: ProbeSchedule
  }
  remark: string
  rule_names?: string[]
}

export interface ProbeTemplate {
  id: number
  name: string
  interval_seconds: number
  slow_threshold_seconds: number | null
  sort_mode: 'stable' | 'latency'
  schedule: ProbeSchedule
  remark: string
  ref_count?: number
  ref_names?: string[]
}

export interface ProbeUnit {
  key: string
  upstream: string
  upstream_name: string
  model: string
  groups: string[]
  group_kinds: Record<string, 'static' | 'rule'>
  sources: string[]
  interval: number
  schedule: ProbeSchedule
  schedules: ProbeSchedule[]
  latency: number | null
  status: string
  last_check: number
  stale: boolean
  active_now: boolean
}

export interface ProbePlan {
  summary: {
    unit_count: number
    member_refs: number
    dedup_saved: number
    daily_requests: number
    global_interval: number
    aggregation_count: number
  }
  units: ProbeUnit[]
}

// ---------- 聚合 ----------

export function listAggregations() {
  return request.get('/admin/api/aggregations')
}

/** 聚合名可能含 /，统一走 query 参数 */
export function saveAggregation(name: string, data: Record<string, unknown>) {
  return request.put('/admin/api/aggregations', data, { params: { name } })
}

export function deleteAggregation(name: string) {
  return request.delete('/admin/api/aggregations', { params: { name } })
}

/** rule 聚合的探测对象：所有路由规则候选的并集 */
export function listRuleUnits() {
  return request.get('/admin/api/aggregations/rule-units')
}

// ---------- 探测模板 ----------

export function listProbeTemplates() {
  return request.get('/admin/api/probe-templates')
}

export function createProbeTemplate(data: Omit<ProbeTemplate, 'id'>) {
  return request.post('/admin/api/probe-templates', data)
}

export function updateProbeTemplate(id: number, data: Omit<ProbeTemplate, 'id'>) {
  return request.put(`/admin/api/probe-templates/${id}`, data)
}

export function deleteProbeTemplate(id: number) {
  return request.delete(`/admin/api/probe-templates/${id}`)
}

// ---------- 探测计划 ----------

export function getProbePlan() {
  return request.get('/admin/api/probe-plan')
}
