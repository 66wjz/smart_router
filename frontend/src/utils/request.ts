import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getToken, removeToken } from '@/utils/auth'
import router from '@/router'

const service = axios.create({
  baseURL: '',
  timeout: 15000,
})

// 请求拦截器：自动携带 JWT
service.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：统一错误处理 + 401 跳登录
service.interceptors.response.use(
  (response) => response.data,
  (error) => {
    let msg = '网络错误'
    if (error.response) {
      const status = error.response.status
      if (status === 401) {
        // CH-049：登录接口的 401 表示「账号或密码不对」，不是会话过期。
        // 以前一律提示「未登录或登录已过期」并清 token 跳登录页 ——
        // 既掩盖了真实原因，又做了无意义的状态清理（本来就在登录页）。
        if (isLoginRequest(error.config?.url)) {
          msg = error.response.data?.detail || '用户名或密码错误'
        } else {
          msg = error.response.data?.detail || '未登录或登录已过期'
          removeToken()
          router.push('/login')
        }
      } else if (status === 403) {
        msg = '无权限访问'
      } else if (status === 404) {
        msg = '请求的资源不存在'
      } else if (status >= 500) {
        msg = '服务器错误'
      } else {
        msg = error.response.data?.detail || `请求失败 (${status})`
      }
    } else if (error.code === 'ECONNABORTED') {
      msg = '请求超时'
    }
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

/** 是否为登录请求（这类 401 是「密码错」，不是「会话过期」） */
function isLoginRequest(url?: string): boolean {
  return Boolean(url && url.includes('/admin/api/login'))
}

export default service
