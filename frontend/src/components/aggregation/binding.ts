/** 聚合编辑器共享类型与纯函数（CH-026 从 Aggregated.vue 抽出） */

export interface MemberItem {
  upstream: string
  model: string
  weight: number
}

export interface BindItem {
  name: string
  match: any
  candidates: any[]
  used: boolean
  /** 该规则内全部候选都勾选 → 保存为 candidates: null（跟随） */
  followAll: boolean
  picked: string[]
}

export function candKey(c: any): string {
  return `${c.upstream}|${c.model}`
}

/** 规则匹配条件的可读文案 */
export function matchText(match: any): string {
  if (!match) return ''
  const parts: string[] = []
  if (match.has_image) parts.push('含图片')
  if (match.has_tools) parts.push('含工具调用')
  if (match.default) parts.push('默认')
  if (Array.isArray(match.content_keywords) && match.content_keywords.length) {
    parts.push(`关键词: ${match.content_keywords.join('/')}`)
  }
  return parts.join(' + ') || '无条件'
}

/** 由规则表 + 已有绑定构造编辑用目录 */
export function buildCatalog(rules: any[], agg?: { rule_bindings?: any } | null): BindItem[] {
  const bindings = agg?.rule_bindings || null
  return (rules || []).map((r: any) => {
    const candidates = (r.candidates || []).filter((c: any) => c.model)
    const binding = bindings?.find((b: any) => b.rule === r.name)
    const used = bindings ? Boolean(binding) : true
    let picked: string[]
    let followAll: boolean
    if (!bindings) {
      // 无绑定（新建或全跟随）→ 全选且标记跟随
      picked = candidates.map(candKey)
      followAll = true
    } else if (used && binding?.candidates == null) {
      picked = candidates.map(candKey)
      followAll = true
    } else if (used) {
      picked = (binding?.candidates || []).map(candKey)
      followAll = picked.length === candidates.length
    } else {
      picked = []
      followAll = false
    }
    return { name: r.name, match: r.match, candidates, used, followAll, picked }
  })
}

/** 把勾选结果转成 rule_bindings 结构；返回 null 表示无有效绑定 */
export function collectBindings(catalog: BindItem[]): any[] | null {
  const used = catalog.filter((i) => i.used && i.picked.length)
  if (!used.length) return null
  return used.map((i) => ({
    rule: i.name,
    // 全部勾选 → null（跟随，规则以后加模型自动纳入）
    candidates: i.followAll ? null : i.picked.map((k) => {
      const [upstream, model] = k.split('|')
      return { upstream, model }
    }),
  }))
}
