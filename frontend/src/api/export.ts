import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getToken, removeToken } from '@/utils/auth'
import router from '@/router'

/**
 * 导出专用的 axios 实例（CH-042）
 *
 * 为什么不复用 utils/request：
 *   它的响应拦截器 `return response.data`，会丢掉 `Content-Disposition`，
 *   而导出需要从这个头里拿服务端生成的中文文件名。这里保留完整响应，
 *   且不改共享实例，避免影响其他页面的现有行为。
 */
const raw = axios.create({
  baseURL: '',
  timeout: 120000,   // 全量导出可能上万条，给足时间
})

raw.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

raw.interceptors.response.use(
  (r) => r,
  (error) => {
    const status = error?.response?.status
    if (status === 401) {
      removeToken()
      router.push('/login')
      ElMessage.error('未登录或登录已过期')
    } else if (error?.response?.data instanceof Blob) {
      // 后端报错时返回的是 JSON，但 responseType=blob 会包成 Blob，需要读出来
      error.response.data.text().then((t: string) => {
        try {
          ElMessage.error(JSON.parse(t)?.detail || '导出失败')
        } catch {
          ElMessage.error('导出失败')
        }
      })
    } else {
      ElMessage.error(error?.message || '导出失败')
    }
    return Promise.reject(error)
  },
)

/** 可导出数据集（与后端 /admin/api/export/{dataset} 一致） */
export type ExportDataset =
  | 'pointers'
  | 'api-keys'
  | 'filter-rules'
  | 'usage-by-model'
  | 'usage-by-unit'
  | 'usage-by-key'
  | 'usage-logs'
  | 'groups'
  | 'probe-templates'
  | 'probe-units'

function pickFilename(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  // 优先读 RFC 5987 的 filename*=UTF-8''xxx —— 中文名在这里
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (star) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      /* 解码失败就退回默认名 */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  return plain ? plain[1] : fallback
}

function saveBlob(data: BlobPart, filename: string) {
  const blob = new Blob([data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // 立即 revoke 会让部分浏览器来不及开始下载
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** 导出全部（受当前筛选条件约束） */
export async function exportAll(
  dataset: ExportDataset,
  params: Record<string, string> = {},
): Promise<void> {
  const res = await raw.get(`/admin/api/export/${dataset}`, {
    params,
    responseType: 'blob',
  })
  saveBlob(
    res.data,
    pickFilename(res.headers['content-disposition'], `${dataset}.xlsx`),
  )
}

/** 批量导出：只导出选中的记录 */
export async function exportBatch(
  dataset: ExportDataset,
  ids: string[],
): Promise<void> {
  const res = await raw.post(
    `/admin/api/export/${dataset}`,
    { ids },
    { responseType: 'blob' },
  )
  saveBlob(
    res.data,
    pickFilename(res.headers['content-disposition'], `${dataset}-选中.xlsx`),
  )
}
