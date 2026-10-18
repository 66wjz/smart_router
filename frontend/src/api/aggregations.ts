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

export interface RuleBindingCandidate {
  upstream: string
  model: string
}

/** 规则绑定：candidates=null 表示该规则内全部候选跟随 */
export interface RuleBinding {
  rule: string
  candidates: RuleBindingCandidate[] | null
}

export interface RuleBindingSummary {
  rule_count: number
  candidate_count: number
  items: { rule: string; count: number; follow_all: boolean }[]
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
  /** CH-024：仅 rule 聚合，null = 全跟随 */
  rule_bindings?: RuleBinding[] | null
  rule_binding_summary?: RuleBindingSummary | null
  /** CH-024：失效的绑定（规则被删 / 候选被移除） */
  stale_bindings?: { rule: string; reason: string; candidate?: RuleBindingCandidate }[]
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

/** rule 聚合的探测对象：所有路由规则候选的并集；传 name 则只算该聚合的绑定 */
export function listRuleUnits(name?: string) {
  return request.get('/admin/api/aggregations/rule-units', { params: name ? { name } : {} })
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
