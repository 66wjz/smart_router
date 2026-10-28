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
  /** CH-034：聚合自身可用分组；空 = 所有 Key 可用 */
  groups: string[]
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
  /** CH-052：会话亲和；null=跟随全局，0=关闭，1=开启 */
  affinity?: number | null
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

/** 保存聚合列表的人工拖拽顺序（CH-028） */
export function reorderAggregations(names: string[]) {
  return request.put('/admin/api/aggregations/order', { names })
}

/** rule 聚合的探测对象：所有路由规则候选的并集；传 name 则只算该聚合的绑定 */
export function listRuleUnits(name?: string) {
  return request.get('/admin/api/aggregations/rule-units', { params: name ? { name } : {} })
}

// ---------- 聚合测试（CH-051） ----------

export interface AggregationTestMember {
  upstream: string
  model: string
  /** static 成员的权重；rule 聚合为 null */
  weight: number | null
  /** 该成员在启用成员里占的请求比例（0-1）；rule 聚合为 null */
  share: number | null
  /** 是否处于健康冷却（冷却中不参与权重分发） */
  cooling: boolean
  status: 'ok' | 'fail' | 'skipped'
  latency_ms?: number
  content?: string | null
  error?: string | null
}

export interface AggregationTestAttempt {
  upstream: string
  model: string
  ok: boolean
  latency_ms: number
  error?: string | null
}

export interface AggregationTestAggregate {
  ok: boolean
  mode: string
  candidate_count: number
  candidates: { upstream: string; model: string; weight?: number }[]
  served: { upstream: string; model: string; latency_ms: number; content?: string | null } | null
  tried: AggregationTestAttempt[]
  error: string | null
}

export interface AggregationTestResult {
  ok: boolean
  name: string
  kind: 'static' | 'rule'
  prompt: string
  members: AggregationTestMember[]
  summary: { total: number; ok: number; fail: number; skipped: number }
  aggregate: AggregationTestAggregate | null
  truncated: boolean
}

/** 聚合名可能含 /，统一走 query 参数 */
export function testAggregation(name: string, data: { prompt?: string; include_aggregate?: boolean } = {}) {
  return request.post('/admin/api/aggregations/test', data, { params: { name } })
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
