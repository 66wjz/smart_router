<template>
  <div class="app-layout">
    <!-- Top bar -->
    <div class="top-nav">
      <div class="top-nav-brand">
        <div class="logo-icon">
          <BaseIcon name="cpu" :size="16" color="#fff" />
        </div>
        <span>Smart Router</span>
        <span class="brand-sub">v5.2 · 管理后台</span>
      </div>
      <div class="top-nav-right">
        <div class="user-dropdown-wrapper">
          <BaseButton variant="icon" class="user-trigger" @click="toggleUserMenu">
            <div class="user-avatar">A</div>
            <span class="user-name">admin</span>
            <BaseIcon name="chevron-down" :size="12" class="user-chevron"
              :style="{ transform: showUserMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }" />
          </BaseButton>
          <div v-if="showUserMenu" class="user-dropdown">
            <div class="dropdown-item" @click="openPasswordDialog">
              <BaseIcon name="lock" :size="14" />
              <span>修改密码</span>
            </div>
            <div class="dropdown-divider"></div>
            <div class="dropdown-item dropdown-item-danger" @click="handleLogout">
              <BaseIcon name="log-out" :size="14" />
              <span>退出登录</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="main-area">
      <!-- Sidebar -->
      <BaseSidebar
        :active-key="activeMenuKey"
        :groups="sidebarGroups"
        :collapsible="true"
        @select="handleMenuSelect"
      />

      <!-- Content Area -->
      <div class="content-area">
        <router-view />
      </div>
    </div>

    <!-- 修改密码弹窗 -->
    <BaseModal :visible="pwdVisible" title="修改密码" @update:visible="pwdVisible = $event">
      <BaseFormGroup label="当前密码" required>
        <BaseInput v-model="pwdForm.old_password" type="password" placeholder="请输入当前密码" />
      </BaseFormGroup>
      <BaseFormGroup label="新密码" required :error="pwdErrors.new_password">
        <BaseInput v-model="pwdForm.new_password" type="password" placeholder="至少 6 位" />
      </BaseFormGroup>
      <BaseFormGroup label="确认新密码" required :error="pwdErrors.confirm">
        <BaseInput v-model="pwdForm.confirm" type="password" placeholder="再次输入新密码" />
      </BaseFormGroup>
      <template #footer>
        <BaseButton variant="ghost" size="sm" @click="pwdVisible = false">取消</BaseButton>
        <BaseButton variant="primary" size="sm" :disabled="pwdLoading" @click="handleChangePwd">
          {{ pwdLoading ? '提交中...' : '确定' }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import BaseSidebar from '@/components/layout/BaseSidebar.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import BaseModal from '@/components/base/BaseModal.vue'
import BaseFormGroup from '@/components/base/BaseFormGroup.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { useUserStore } from '@/stores/user'
import { changePassword } from '@/api/common'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const sidebarGroups = [
  {
    label: '',
    items: [
      { key: 'dashboard', label: '仪表盘', icon: 'gauge', path: '/dashboard' },
      { key: 'api-keys', label: 'API Key 管理', icon: 'key', path: '/api-keys' },
      { key: 'upstreams', label: '上游源管理', icon: 'server', path: '/upstreams' },
      { key: 'pointers', label: '模型别名', icon: 'link', path: '/pointers' },
    ],
  },
  {
    label: '智能路由',
    icon: 'network',
    collapsible: true,
    items: [
      { key: 'rules', label: '路由规则', icon: 'sliders-horizontal', path: '/rules' },
      { key: 'aggregated', label: '聚合模型', icon: 'collection', path: '/aggregated' },
    ],
  },
  {
    label: '统计',
    icon: 'bar-chart',
    collapsible: true,
    items: [
      { key: 'usage', label: '用量统计', icon: 'bar-chart', path: '/usage' },
    ],
  },
  {
    label: '',
    items: [
      { key: 'settings', label: '系统设置', icon: 'settings', path: '/settings' },
    ],
  },
]

const allMenuItems = sidebarGroups.flatMap((g) => g.items)

const activeMenuKey = computed(() => {
  const path = route.path
  for (const item of allMenuItems) {
    if (path === item.path || path.startsWith(item.path + '/')) return item.key
  }
  return ''
})

function handleMenuSelect(key: string) {
  const item = allMenuItems.find((i) => i.key === key)
  if (item) router.push(item.path)
}

// ---- 用户菜单 ----
const showUserMenu = ref(false)
function toggleUserMenu() {
  showUserMenu.value = !showUserMenu.value
}
function handleClickOutside(e: MouseEvent) {
  const wrapper = document.querySelector('.user-dropdown-wrapper')
  if (wrapper && !wrapper.contains(e.target as Node)) {
    showUserMenu.value = false
  }
}
onMounted(() => document.addEventListener('click', handleClickOutside))
onUnmounted(() => document.removeEventListener('click', handleClickOutside))

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  userStore.logout()
  router.push('/login')
}

// ---- 修改密码 ----
const pwdVisible = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdErrors = reactive({ new_password: '', confirm: '' })

function openPasswordDialog() {
  showUserMenu.value = false
  pwdVisible.value = true
}

async function handleChangePwd() {
  pwdErrors.new_password = pwdForm.new_password.length < 6 ? '新密码至少 6 位' : ''
  pwdErrors.confirm = pwdForm.confirm !== pwdForm.new_password ? '两次输入不一致' : ''
  if (pwdErrors.new_password || pwdErrors.confirm) return
  pwdLoading.value = true
  try {
    await changePassword({ old_password: pwdForm.old_password, new_password: pwdForm.new_password })
    ElMessage.success('密码已修改')
    pwdVisible.value = false
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm = ''
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.top-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 16px;
  background: var(--bg-base);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  z-index: var(--z-sticky);
}

.top-nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.brand-sub {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.logo-icon {
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-blue-hover));
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.top-nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-dropdown-wrapper {
  position: relative;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
}
.user-trigger:hover {
  background: var(--bg-hover);
}

.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-blue-hover));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.user-chevron {
  color: var(--text-tertiary);
}

.user-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 128px;
  width: max-content;
  background: var(--bg-base);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: var(--z-dropdown);
  overflow: hidden;
  padding: 4px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.dropdown-item:hover {
  background: var(--bg-hover);
}
.dropdown-item-danger {
  color: var(--accent-red);
}
.dropdown-item-danger:hover {
  background: var(--accent-red-muted);
}
.dropdown-divider {
  height: 1px;
  background: var(--border-subtle);
  margin: 4px 0;
}

.main-area {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-deep);
  padding: 20px;
  overflow-y: auto;
}
</style>
