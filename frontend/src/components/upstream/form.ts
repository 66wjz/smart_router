/** 上游源表单模型与纯工具（CH-026 抽出） */

export interface UpstreamForm {
  id: string
  name: string
  base_url: string
  format: string
  groups: string[]
  probe_enabled: boolean
  smart_retry: boolean
}

export function emptyForm(): UpstreamForm {
  return {
    id: '',
    name: '',
    base_url: '',
    format: 'openai',
    groups: ['free'],
    probe_enabled: true,
    smart_retry: false,
  }
}

/** 多行文本 → Key 数组（去空行、去首尾空白） */
export function parseKeys(text: string): string[] {
  return (text || '')
    .split('\n')
    .map((k) => k.trim())
    .filter((k) => k)
}

/** Base URL 实时拼接预览（容错已含目标路径的情况） */
export function buildEndpointPreview(baseUrl: string, path: string): string {
  const base = (baseUrl || '').trim().replace(/\/+$/, '')
  if (!base) return ''
  if (base.endsWith(path)) return base
  return `${base}${path}`
}
