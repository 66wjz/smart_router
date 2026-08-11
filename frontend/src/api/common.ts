import request from '@/utils/request'

// 登录
export function login(data: { username: string; password: string }) {
  return request.post('/admin/api/login', data)
}

// 修改密码
export function changePassword(data: { old_password: string; new_password: string }) {
  return request.put('/admin/api/admin-password', data)
}

// 热重载
export function reloadConfig() {
  return request.post('/admin/api/reload')
}

// 仪表盘
export function getDashboard() {
  return request.get('/admin/api/dashboard')
}

// 状态面板
export function getStatus() {
  return request.get('/status')
}
