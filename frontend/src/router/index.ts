import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/utils/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/',
      component: () => import('@/layouts/AdminLayout.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { title: '仪表盘', icon: 'Odometer' },
        },
        {
          path: 'api-keys',
          name: 'ApiKeys',
          component: () => import('@/views/ApiKeys.vue'),
          meta: { title: 'API Key 管理', icon: 'Key' },
        },
        {
          path: 'upstreams',
          name: 'Upstreams',
          component: () => import('@/views/Upstreams.vue'),
          meta: { title: '上游源管理', icon: 'Connection' },
        },
        {
          path: 'rules',
          name: 'Rules',
          component: () => import('@/views/Rules.vue'),
          meta: { title: '路由规则', icon: 'SetUp' },
        },
        {
          path: 'pointers',
          name: 'Pointers',
          component: () => import('@/views/Pointers.vue'),
          meta: { title: '模型别名', icon: 'Link' },
        },
        {
          path: 'aggregated',
          name: 'Aggregated',
          component: () => import('@/views/Aggregated.vue'),
          meta: { title: '聚合模型', icon: 'Collection' },
        },
        // CH-023：延迟面板并入「聚合模型 → 探测计划」，旧书签重定向
        {
          path: 'latency',
          redirect: { path: '/aggregated', query: { tab: 'plan' } },
        },
        // CH-023：路由参数拆分到「聚合模型 → 探测计划」与「系统设置 → 全局容错」
        {
          path: 'route-params',
          redirect: '/settings',
        },
        {
          path: 'usage',
          name: 'Usage',
          component: () => import('@/views/Usage.vue'),
          meta: { title: '用量统计', icon: 'DataAnalysis' },
        },
        {
          path: 'filter-rules',
          name: 'FilterRules',
          component: () => import('@/views/FilterRules.vue'),
          meta: { title: '请求过滤', icon: 'Shield' },
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/Settings.vue'),
          meta: { title: '系统设置', icon: 'Setting' },
        },
      ],
    },
  ],
})

// 全局前置守卫
router.beforeEach((to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - Smart Router` : 'Smart Router'
  if (to.meta.public) {
    next()
    return
  }
  if (!getToken()) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  next()
})

export default router
