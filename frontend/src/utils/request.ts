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
        msg = '未登录或登录已过期'
        removeToken()
        router.push('/login')
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

export default service
