import request from '@/utils/request'

export interface ModelGroupMember {
  upstream: string
  /** 该上游源里的真实模型名；不填表示与聚合名同名 */
  model?: string
  weight?: number
}

export interface ModelGroup {
  model: string
  sources: string[]
  members: { upstream: string; model: string }[]
  enabled: boolean
  configured: boolean
  auto_sources: string[]
}

export interface GroupSuggestion {
  suggested_name: string
  normalized: string
  members: { upstream: string; upstream_name: string; model: string }[]
}

export function listModelGroups() {
  return request.get('/admin/api/model-groups')
}

/** 聚合名可能含 /，统一走 query 参数 */
export function saveModelGroup(model: string, upstreams: ModelGroupMember[], enabled: boolean) {
  return request.put('/admin/api/model-groups', { upstreams, enabled }, { params: { model } })
}

export function deleteModelGroup(model: string) {
  return request.delete('/admin/api/model-groups', { params: { model } })
}

/** 归一化建议：自动识别"前缀/大小写/符号不同但其实是同一模型"的分组 */
export function listGroupSuggestions() {
  return request.get('/admin/api/model-groups/suggestions')
}

/** 某上游源的已配置模型（添加异名成员时选择真实模型名） */
export function listSourceModels(upstream: string) {
  return request.get('/admin/api/model-groups/source-models', { params: { upstream } })
}

// ---------- 聚合组探测配置（CH-021） ----------

export interface ProbeWindow {
  start: string
  end: string
}

export interface ProbeSchedule {
  mode: 'always' | 'window'
  days: number[]
  windows: ProbeWindow[]
}

export interface GroupProbeConfig {
  enabled: boolean
  interval_seconds: number | null
  slow_threshold_seconds: number | null
  sort_mode: 'stable' | 'latency'
  schedule: ProbeSchedule
}

export interface ProbeUnit {
  key: string
  upstream: string
  upstream_name: string
  model: string
  groups: string[]
  sources: string[]
  interval: number
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
  }
  units: ProbeUnit[]
}

export function listProbeConfigs() {
  return request.get('/admin/api/model-groups/probe-configs')
}

export function saveGroupProbe(model: string, data: GroupProbeConfig) {
  return request.put('/admin/api/model-groups/probe', data, { params: { model } })
}

export function deleteGroupProbe(model: string) {
  return request.delete('/admin/api/model-groups/probe', { params: { model } })
}

/** 全局去重后的探测计划（含成本估算与被引用关系） */
export function getProbePlan() {
  return request.get('/admin/api/model-groups/probe-plan')
}
